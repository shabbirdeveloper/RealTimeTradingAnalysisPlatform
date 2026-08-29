"""
GET /health -- lightweight self-check for this service process (is it up,
is a provider key set, is Supabase configured). Per-asset data freshness
(LIVE/DELAYED/STALE/OFFLINE) lives in the `system_health` table this
service writes to, which the frontend/admin pages read directly from
Supabase -- duplicating that here would just be a second source of truth
to keep in sync, so this endpoint deliberately stays shallow.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.config import get_settings

router = APIRouter()


@router.get("/health")
async def health() -> dict:
    settings = get_settings()
    return {
        "status": "ok",
        "environment": settings.environment,
        "has_real_provider": settings.has_real_provider,
        "has_supabase": settings.has_supabase,
        "poll_interval_seconds": settings.poll_interval_seconds,
    }
