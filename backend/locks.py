"""写入短锁，防并发双写。"""
from __future__ import annotations

import sqlite3
import time
import uuid
from fastapi import APIRouter, Header, HTTPException

from auth import current_user, require_writer
from db import connect, immediate_transaction

router = APIRouter(prefix="/api/locks", tags=["locks"])


def _new_request_id() -> str:
    return uuid.uuid4().hex


def acquire_on_conn(conn, lock_key: str, holder: str, ttl_sec: int = 20, request_id: str | None = None) -> str:
    """在调用方已持有的写事务连接内取锁（与发布落行同一事务、同一库写锁）。

    锁行写入与 publications 落行共享一个 BEGIN IMMEDIATE：并发第二路在
    开口抢库写锁时即被挡（由调用方把 SQLITE_BUSY 归一为 409），无等待顶替。
    纯 INSERT，不做 UPSERT；过期锁先删后插。
    """
    request_id = request_id or _new_request_id()
    lock_holder = f"{holder}:{request_id}"
    now = time.time()
    row = conn.execute(
        "SELECT holder, expires_at FROM write_locks WHERE lock_key=?",
        (lock_key,),
    ).fetchone()
    if row and row["expires_at"] > now and row["holder"] != lock_holder:
        raise HTTPException(409, f"资源锁定中：{row['holder'].split(':', 1)[0]}")
    if row:  # 过期或本请求重入：清掉旧锁行再插
        conn.execute("DELETE FROM write_locks WHERE lock_key=?", (lock_key,))
    conn.execute(
        "INSERT INTO write_locks(lock_key,holder,expires_at) VALUES(?,?,?)",
        (lock_key, lock_holder, now + ttl_sec),
    )
    return request_id


def acquire(lock_key: str, holder: str, ttl_sec: int = 20, request_id: str | None = None) -> str:
    """取锁并返回本次占用的请求令牌；release 必须持同令牌才准放行。

    signboard-01 争用修复（同屏发布场控互斥）。旧实现两处致命缺陷：
    1. 按 holder 判重，同一编排员的并发请求互相视为同持锁人，锁被静默重入；
    2. UPSERT 顶替，后到者直接覆盖先到者的占用。

    现口径：
    - 只读连接先做快速失败：读到已提交占用立即 409，不抢库写锁；
    - 插锁走 BEGIN IMMEDIATE，进入即独占库写锁；并发第二路抢锁时拿到
      SQLITE_BUSY，归一为 409；锁行已存在则唯一约束报错，绝无顶替；
    - 每次占用发唯一 request_id，release 凭令牌只解自己的锁；
    - 相同 request_id 视为同一请求重试，允许重入。
    """
    request_id = request_id or _new_request_id()
    lock_holder = f"{holder}:{request_id}"
    now = time.time()
    with connect() as ro:
        row = ro.execute(
            "SELECT holder, expires_at FROM write_locks WHERE lock_key=?",
            (lock_key,),
        ).fetchone()
        if row and row["expires_at"] > now and row["holder"] != lock_holder:
            raise HTTPException(409, f"资源锁定中：{row['holder'].split(':', 1)[0]}")
    try:
        # 锁路径短 busy 超时：争用败方 ~1.5s 内拿到 409，不长等
        with immediate_transaction(timeout=1.5) as conn:
            fresh = conn.execute(
                "SELECT holder, expires_at FROM write_locks WHERE lock_key=?",
                (lock_key,),
            ).fetchone()
            if fresh and fresh["expires_at"] > now and fresh["holder"] != lock_holder:
                raise HTTPException(409, f"资源锁定中：{fresh['holder'].split(':', 1)[0]}")
            # 纯 INSERT：锁行已存在且未过期时唯一约束报错，不做顶替
            conn.execute(
                "INSERT INTO write_locks(lock_key,holder,expires_at) VALUES(?,?,?)",
                (lock_key, lock_holder, now + ttl_sec),
            )
    except sqlite3.IntegrityError as exc:
        raise HTTPException(409, "资源锁定中，请重试") from exc
    except sqlite3.OperationalError as exc:
        # SQLITE_BUSY：另一路正持库写锁，互斥败方
        raise HTTPException(409, "同屏发布争用中，请稍后重试") from exc
    return request_id


def release(lock_key: str, holder: str, request_id: str | None = None) -> None:
    """释放锁。带 request_id 时只准释放本请求自己的占用。"""
    with connect() as conn:
        if request_id:
            conn.execute(
                "DELETE FROM write_locks WHERE lock_key=? AND holder=?",
                (lock_key, f"{holder}:{request_id}"),
            )
        else:
            conn.execute(
                "DELETE FROM write_locks WHERE lock_key=? AND holder LIKE ?",
                (lock_key, f"{holder}:%"),
            )
        conn.commit()


@router.post("/acquire")
def api_acquire(body: dict, authorization: str | None = Header(default=None)):
    user = current_user(authorization)
    require_writer(user)
    key = (body.get("lock_key") or "").strip()
    if not key:
        raise HTTPException(400, "缺少 lock_key")
    rid = acquire(key, user["username"], int(body.get("ttl_sec") or 20), body.get("request_id"))
    return {"ok": True, "lock_key": key, "holder": user["username"], "request_id": rid}


@router.post("/release")
def api_release(body: dict, authorization: str | None = Header(default=None)):
    user = current_user(authorization)
    require_writer(user)
    key = (body.get("lock_key") or "").strip()
    release(key, user["username"], body.get("request_id"))
    return {"ok": True}
