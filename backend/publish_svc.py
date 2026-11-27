"""发布上屏（正式事务 vs 影子升正 空桩可扩展）。

signboard-01 正确性口径（甲路径，禁止第三路）：
风险等级 >=4 的分区，正式上屏必须同票写入场控单号；缺号整笔拒写，
publications 正式行零增。乙路径影子草案可无票建立，但升正落正式区
前必须补票，未补票升正同样整笔拒写、正式发布表零改。
"""
from __future__ import annotations

import sqlite3
import time
from contextlib import contextmanager

from fastapi import APIRouter, Header, HTTPException

from audit_svc import write_audit, write_history
from auth import current_user, require_writer
from db import connect, immediate_transaction, rows_to_list
from locks import acquire_on_conn, release
from policies import assert_field_ticket_for_risk, assert_playlist_ready, assert_screen_online, assert_window_open
from validators import require_positive_int, require_title

router = APIRouter(prefix="/api/publish", tags=["publish"])


@contextmanager
def publish_mutex(lock_key: str, holder: str):
    """同屏发布互斥临界区。

    单条 BEGIN IMMEDIATE（busy 超时 0）从开口持有到提交：取锁行与正式
    落行同事务、同库写锁。并发第二路开口即 SQLITE_BUSY，不等待、不顶替，
    归一为 409。锁表保留占用痕迹供查询与 TTL 兜底。
    """
    request_id = None
    try:
        with immediate_transaction(timeout=0) as conn:
            request_id = acquire_on_conn(conn, lock_key, holder)
            yield conn
    except sqlite3.OperationalError as exc:  # SQLITE_BUSY：互斥败方
        raise HTTPException(409, "同屏发布争用中，请稍后重试") from exc
    except sqlite3.IntegrityError as exc:  # 锁行唯一竞争
        raise HTTPException(409, "资源锁定中，请重试") from exc
    finally:
        if request_id:
            release(lock_key, holder, request_id)


@router.get("/official")
def list_official(authorization: str | None = Header(default=None)):
    current_user(authorization)
    with connect() as conn:
        rows = rows_to_list(
            conn.execute(
                """
                SELECT p.*, s.code screen_code, s.title screen_title,
                       pl.code playlist_code, w.code window_code,
                       z.risk_level, z.code zone_code
                FROM publications p
                JOIN screens s ON s.id=p.screen_id
                JOIN zones z ON z.id=s.zone_id
                JOIN playlists pl ON pl.id=p.playlist_id
                JOIN time_windows w ON w.id=p.window_id
                WHERE p.official=1
                ORDER BY p.id DESC
                """
            ).fetchall()
        )
    return {"items": rows}


@router.get("/shadows")
def list_shadows(authorization: str | None = Header(default=None)):
    current_user(authorization)
    with connect() as conn:
        rows = rows_to_list(
            conn.execute(
                """
                SELECT sh.*, s.code screen_code, pl.code playlist_code, w.code window_code,
                       z.risk_level, z.code zone_code
                FROM publish_shadows sh
                JOIN screens s ON s.id=sh.screen_id
                JOIN zones z ON z.id=s.zone_id
                JOIN playlists pl ON pl.id=sh.playlist_id
                JOIN time_windows w ON w.id=sh.window_id
                ORDER BY sh.id DESC
                """
            ).fetchall()
        )
    return {"items": rows}


def _load_refs(conn, screen_id, playlist_id, window_id):
    screen = conn.execute(
        "SELECT s.*, z.risk_level FROM screens s JOIN zones z ON z.id=s.zone_id WHERE s.id=?",
        (screen_id,),
    ).fetchone()
    playlist = conn.execute("SELECT * FROM playlists WHERE id=?", (playlist_id,)).fetchone()
    window = conn.execute("SELECT * FROM time_windows WHERE id=?", (window_id,)).fetchone()
    if not screen or not playlist or not window:
        raise HTTPException(404, "屏幕/清单/时段窗不存在")
    assert_screen_online(screen["status"])
    assert_playlist_ready(playlist["status"])
    assert_window_open(window["status"])
    return screen, playlist, window


@router.post("/official")
def publish_official(body: dict, authorization: str | None = Header(default=None)):
    """甲路径：同事务写入正式发布并升版本；高风险缺场控单整笔拒写。"""
    user = current_user(authorization)
    require_writer(user)
    screen_id = require_positive_int(body.get("screen_id"), "屏幕编号")
    playlist_id = require_positive_int(body.get("playlist_id"), "清单编号")
    window_id = require_positive_int(body.get("window_id"), "时段编号")
    summary = require_title(body.get("summary") or "正式发布", "发布摘要")
    layout_id = body.get("layout_id")
    lock_key = f"publish:{screen_id}"
    # 单事务：取锁 + 风险闸 + 版本计算 + 正式落行原子；并发败方 409 且零增
    with publish_mutex(lock_key, user["username"]) as conn:
        screen, _playlist, _window = _load_refs(conn, screen_id, playlist_id, window_id)
        # 风险闸在事务内、任何正式行写入前；缺号抛 400，事务回滚零增
        ticket_no = assert_field_ticket_for_risk(screen["risk_level"], body.get("field_ticket_no"))
        prev = conn.execute(
            "SELECT version FROM publications WHERE screen_id=? AND official=1",
            (screen_id,),
        ).fetchone()
        version = (prev["version"] + 1) if prev else 1
        conn.execute("DELETE FROM publications WHERE screen_id=? AND official=1", (screen_id,))
        cur = conn.execute(
            "INSERT INTO publications(screen_id,playlist_id,window_id,layout_id,version,summary,status,official,field_ticket_no,published_at,published_by) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (
                screen_id,
                playlist_id,
                window_id,
                layout_id,
                version,
                summary,
                "published",
                1,
                ticket_no,
                time.time(),
                user["username"],
            ),
        )
        pid = cur.lastrowid
    # 同票贯穿历史与审计：拒写时此行不会执行，无成功痕迹
    write_history(
        "publication",
        pid,
        "publish_official",
        f"{summary}｜场控单号 {ticket_no or '—'}",
        user["username"],
    )
    write_audit(
        user["username"],
        "publish.official",
        {"id": pid, "version": version, "field_ticket_no": ticket_no},
    )
    return {"id": pid, "version": version, "path": "official", "field_ticket_no": ticket_no}


@router.post("/shadow")
def create_shadow(body: dict, authorization: str | None = Header(default=None)):
    """乙路径第一步：只写影子草案，正式区零改。高风险允许无票挂起，升正前补票。"""
    user = current_user(authorization)
    require_writer(user)
    screen_id = require_positive_int(body.get("screen_id"), "屏幕编号")
    playlist_id = require_positive_int(body.get("playlist_id"), "清单编号")
    window_id = require_positive_int(body.get("window_id"), "时段编号")
    summary = require_title(body.get("summary") or "影子发布草案", "发布摘要")
    layout_id = body.get("layout_id")
    with connect() as conn:
        screen, _playlist, _window = _load_refs(conn, screen_id, playlist_id, window_id)
        # 草案阶段不卡票：高风险影子可先挂起，升正前必须补票
        ticket_no = (body.get("field_ticket_no") or "").strip()
        cur = conn.execute(
            "INSERT INTO publish_shadows(screen_id,playlist_id,window_id,layout_id,summary,status,field_ticket_no,created_at,created_by) VALUES(?,?,?,?,?,?,?,?,?)",
            (
                screen_id,
                playlist_id,
                window_id,
                layout_id,
                summary,
                "open",
                ticket_no,
                time.time(),
                user["username"],
            ),
        )
        sid = cur.lastrowid
        conn.commit()
    write_history("publish_shadow", sid, "create", f"{summary}｜场控单号 {ticket_no or '待补'}", user["username"])
    return {"id": sid, "path": "shadow", "status": "open", "field_ticket_no": ticket_no}


@router.post("/shadow/{shadow_id}/ticket")
def supplement_shadow_ticket(shadow_id: int, body: dict, authorization: str | None = Header(default=None)):
    """乙路径补票：仅待升正影子可补，正式区仍零改。"""
    user = current_user(authorization)
    require_writer(user)
    with connect() as conn:
        sh = conn.execute(
            "SELECT sh.*, z.risk_level FROM publish_shadows sh "
            "JOIN screens s ON s.id=sh.screen_id JOIN zones z ON z.id=s.zone_id WHERE sh.id=?",
            (shadow_id,),
        ).fetchone()
        if not sh:
            raise HTTPException(404, "影子不存在")
        if sh["status"] != "open":
            raise HTTPException(409, "影子不可补票")
        ticket_no = assert_field_ticket_for_risk(sh["risk_level"], body.get("field_ticket_no"))
        conn.execute(
            "UPDATE publish_shadows SET field_ticket_no=? WHERE id=?",
            (ticket_no, shadow_id),
        )
        conn.commit()
    write_history("publish_shadow", shadow_id, "supplement_ticket", f"补场控单号 {ticket_no}", user["username"])
    write_audit(user["username"], "publish.shadow.ticket", {"shadow_id": shadow_id, "field_ticket_no": ticket_no})
    return {"id": shadow_id, "field_ticket_no": ticket_no}


@router.post("/shadow/{shadow_id}/promote")
def promote_shadow(shadow_id: int, body: dict | None = None, authorization: str | None = Header(default=None)):
    """乙路径升正：原子落正式区。高风险影子缺场控单整笔拒写、正式表零改。"""
    user = current_user(authorization)
    require_writer(user)
    body = body or {}
    with connect() as conn:
        sh = conn.execute("SELECT * FROM publish_shadows WHERE id=?", (shadow_id,)).fetchone()
        if not sh:
            raise HTTPException(404, "影子不存在")
        if sh["status"] != "open":
            raise HTTPException(409, "影子不可升正")
        screen_id = sh["screen_id"]
    lock_key = f"publish:{screen_id}"
    with publish_mutex(lock_key, user["username"]) as conn:
        sh = conn.execute(
            "SELECT sh.*, z.risk_level FROM publish_shadows sh "
            "JOIN screens s ON s.id=sh.screen_id JOIN zones z ON z.id=s.zone_id WHERE sh.id=?",
            (shadow_id,),
        ).fetchone()
        _load_refs(conn, sh["screen_id"], sh["playlist_id"], sh["window_id"])
        # 请求体可带票（等同于升正前补票）；否则以影子已存票为准，缺号整笔拒写
        raw_ticket = body.get("field_ticket_no") if body.get("field_ticket_no") is not None else sh["field_ticket_no"]
        ticket_no = assert_field_ticket_for_risk(sh["risk_level"], raw_ticket)
        prev = conn.execute(
            "SELECT version FROM publications WHERE screen_id=? AND official=1",
            (sh["screen_id"],),
        ).fetchone()
        version = (prev["version"] + 1) if prev else 1
        conn.execute("DELETE FROM publications WHERE screen_id=? AND official=1", (sh["screen_id"],))
        cur = conn.execute(
            "INSERT INTO publications(screen_id,playlist_id,window_id,layout_id,version,summary,status,official,field_ticket_no,published_at,published_by) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (
                sh["screen_id"],
                sh["playlist_id"],
                sh["window_id"],
                sh["layout_id"],
                version,
                sh["summary"],
                "published",
                1,
                ticket_no,
                time.time(),
                user["username"],
            ),
        )
        pid = cur.lastrowid
        conn.execute(
            "UPDATE publish_shadows SET status='promoted', field_ticket_no=? WHERE id=?",
            (ticket_no, shadow_id),
        )
    write_history(
        "publication",
        pid,
        "promote_shadow",
        f"升正影子 {shadow_id}｜场控单号 {ticket_no or '—'}",
        user["username"],
    )
    write_audit(
        user["username"],
        "publish.promote",
        {"shadow_id": shadow_id, "id": pid, "field_ticket_no": ticket_no},
    )
    return {"id": pid, "version": version, "path": "shadow_promote", "field_ticket_no": ticket_no}
