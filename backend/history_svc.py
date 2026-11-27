"""变更历史。"""
from __future__ import annotations

from fastapi import APIRouter, Header

from auth import current_user
from db import connect, rows_to_list

router = APIRouter(prefix="/api/history", tags=["history"])


@router.get("")
def list_history(
    limit: int = 100,
    entity_kind: str | None = None,
    action: str | None = None,
    authorization: str | None = Header(default=None),
):
    current_user(authorization)
    sql = "SELECT * FROM change_history WHERE 1=1"
    params: list = []
    if entity_kind:
        sql += " AND entity_kind=?"
        params.append(entity_kind.strip())
    if action:
        sql += " AND action=?"
        params.append(action.strip())
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(max(1, min(limit, 300)))
    with connect() as conn:
        rows = rows_to_list(conn.execute(sql, params).fetchall())
    return {"items": rows}
