"""审计与辅助查询。"""
from __future__ import annotations

import json
import time
from fastapi import APIRouter, Header

from auth import current_user
from db import connect, rows_to_list

router = APIRouter(prefix="/api/audit", tags=["audit"])


def write_audit(actor: str, action: str, payload: dict) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO audit_log(actor,action,payload,created_at) VALUES(?,?,?,?)",
            (actor, action, json.dumps(payload, ensure_ascii=False), time.time()),
        )
        conn.commit()


def write_history(entity_kind: str, entity_id: int, action: str, detail: str, actor: str) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO change_history(entity_kind,entity_id,action,detail,actor,created_at) VALUES(?,?,?,?,?,?)",
            (entity_kind, entity_id, action, detail, actor, time.time()),
        )
        conn.commit()


@router.get("/recent")
def recent(limit: int = 50, action: str | None = None, authorization: str | None = Header(default=None)):
    current_user(authorization)
    capped = max(1, min(limit, 200))
    with connect() as conn:
        if action:
            rows = conn.execute(
                "SELECT * FROM audit_log WHERE action=? ORDER BY id DESC LIMIT ?",
                (action.strip(), capped),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM audit_log ORDER BY id DESC LIMIT ?",
                (capped,),
            ).fetchall()
    return {"items": rows_to_list(rows)}
