"""
FastAPI application entrypoint for the market-data collector service.

Run locally with:
    uvicorn app.main:app --reload
    (or: py -m uvicorn app.main:app --reload, if `uvicorn`/`python` aren't
    on PATH but the `py` launcher is)

See apps/api/README.md for setup (env vars, demo mode, credit budget).
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import FastAPI

from app.api.routes import admin_backtests as admin_backtest_routes
from app.api.routes import debug as debug_routes
from app.api.routes import health as health_routes
from app.collector.scheduler import run_all_assets, start_scheduler, stop_scheduler
from app.config import get_settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

# httpx logs each request URL at INFO level, which would otherwise print
# TWELVE_DATA_API_KEY in plain text every single poll (it's a query param
# on the Twelve Data request). WARNING still surfaces real httpx problems
# (connection errors, timeouts), just not routine successful requests.
logging.getLogger("httpx").setLevel(logging.WARNING)

app = FastAPI(title="NorthFXTrade Market Data Service", version="0.1.0")
app.include_router(health_routes.router)
app.include_router(debug_routes.router)
app.include_router(admin_backtest_routes.router)


@app.on_event("startup")
async def _on_startup() -> None:
    settings = get_settings()
    if not settings.has_supabase:
        logger.warning(
            "SUPABASE_URL/SUPABASE_SERVICE_ROLE_KEY not set -- the polling "
            "loop will not start. Set them in apps/api/.env (see "
            ".env.example) once a Supabase project exists."
        )
        return

    start_scheduler()
    # Kick off one poll immediately instead of waiting a full interval, so
    # system_health has real data right after startup. Respects market
    # hours like any scheduled run (force=False) -- use POST /debug/poll-now
    # to bypass that for manual testing.
    asyncio.create_task(run_all_assets())


@app.on_event("shutdown")
async def _on_shutdown() -> None:
    stop_scheduler()
