"""总览。"""
from __future__ import annotations

from fastapi import APIRouter, Header

from auth import current_user
from db import PRODUCT_META, connect
from models import TICKET_REQUIRED_RISK

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("")
def dashboard(authorization: str | None = Header(default=None)):
    current_user(authorization)
    with connect() as conn:
        screens = conn.execute("SELECT COUNT(*) c FROM screens").fetchone()["c"]
        online = conn.execute("SELECT COUNT(*) c FROM screens WHERE status='online'").fetchone()["c"]
        assets = conn.execute("SELECT COUNT(*) c FROM assets WHERE status='ready'").fetchone()["c"]
        pubs = conn.execute(
            "SELECT COUNT(*) c FROM publications WHERE official=1 AND status='published'"
        ).fetchone()["c"]
        shadows = conn.execute(
            "SELECT COUNT(*) c FROM publish_shadows WHERE status='open'"
        ).fetchone()["c"]
        high_risk_zones = conn.execute(
            "SELECT COUNT(*) c FROM zones WHERE risk_level>=?",
            (TICKET_REQUIRED_RISK,),
        ).fetchone()["c"]
        ticket_pending_shadows = conn.execute(
            "SELECT COUNT(*) c FROM publish_shadows sh "
            "JOIN screens s ON s.id=sh.screen_id JOIN zones z ON z.id=s.zone_id "
            "WHERE sh.status='open' AND z.risk_level>=? AND sh.field_ticket_no=''",
            (TICKET_REQUIRED_RISK,),
        ).fetchone()["c"]
        panics = conn.execute("SELECT COUNT(*) c FROM panic_events").fetchone()["c"]
        overrides = conn.execute(
            "SELECT COUNT(*) c FROM overrides WHERE official=1 AND active=1"
        ).fetchone()["c"]
    return {
        "product": PRODUCT_META["name"],
        "domain": PRODUCT_META["domain"],
        "sub": PRODUCT_META["sub"],
        "skeleton": PRODUCT_META["skeleton"],
        "screens": screens,
        "online_screens": online,
        "ready_assets": assets,
        "official_publications": pubs,
        "open_shadows": shadows,
        "high_risk_zones": high_risk_zones,
        "ticket_pending_shadows": ticket_pending_shadows,
        "panic_events": panics,
        "active_overrides": overrides,
    }
