"""
Manual testing endpoints. NOT meant to survive into a real deployment --
guarded to only respond when ENVIRONMENT=development (see app/config.py),
so this is safe to leave in the codebase but must not be relied on once
this service runs anywhere public. Before a real deploy, either remove
this router from app/main.py or put real auth in front of it.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.collector.scheduler import run_all_assets
from app.config import get_settings

router = APIRouter(prefix="/debug", tags=["debug"])


@router.post("/poll-now")
async def poll_now() -> dict:
    """Runs one poll cycle immediately, ignoring the market-hours check --
    lets you verify the Twelve Data + Supabase wiring right now instead of
    waiting for the market to be open. Check your terminal's log output
    and the `candles` table in Supabase afterward; this endpoint itself
    just confirms the cycle ran, it doesn't return the fetched data."""
    settings = get_settings()
    if settings.environment != "development":
        raise HTTPException(status_code=404, detail="Not available outside development")

    await run_all_assets(force=True)
    return {"status": "poll cycle triggered -- check the server log and the candles table"}
