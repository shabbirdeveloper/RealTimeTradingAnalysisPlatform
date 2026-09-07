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
from app.api.routes import evaluate as evaluate_routes
from app.api.routes import health as health_routes
from app.collector.scheduler import (
    run_market_engine,
    run_otc_assets,
    start_scheduler,
    stop_scheduler,
)
from app.config import get_settings
from app.keep_awake import allow_sleep, prevent_sleep
from app.logging_setup import configure as configure_logging

_LOG_PATH = configure_logging()
logger = logging.getLogger(__name__)

app = FastAPI(title="NorthFXTrade Market Data Service", version="0.1.0")
app.include_router(health_routes.router)
app.include_router(debug_routes.router)
app.include_router(evaluate_routes.router)
app.include_router(admin_backtest_routes.router)


@app.on_event("startup")
async def _on_startup() -> None:
    if _LOG_PATH:
        logger.info("logging to %s", _LOG_PATH)
    settings = get_settings()
    if not settings.has_supabase:
        logger.warning(
            "SUPABASE_URL/SUPABASE_SERVICE_ROLE_KEY not set -- the polling "
            "loop will not start. Set them in apps/api/.env (see "
            ".env.example) once a Supabase project exists."
        )
        return

    # Ask Windows not to sleep. A sleeping machine collects nothing and
    # leaves no error behind -- and the decisions missed in that window can
    # never be backfilled, only the prices.
    if prevent_sleep():
        logger.info("sleep prevention active — the display can still turn off")
    else:
        logger.info(
            "sleep prevention unavailable on this platform — if this machine "
            "sleeps, collection stops and those gaps cannot be recovered"
        )

    start_scheduler()

    # One cycle immediately instead of waiting a full interval, so the
    # dashboard has a current decision right after startup.
    #
    # This used to call run_all_assets() -- the OLD engine -- and it did so
    # UNCONDITIONALLY, ignoring the flag that decides which engine runs. So
    # every restart wrote one round of 15/30/60-minute decisions from an
    # engine that had been replaced, and a 30-minute signal then blocked the
    # 5-minute engine from publishing on that asset for half an hour. The
    # flag has to gate the startup kick exactly as it gates the schedule,
    # or "which engine is running" has two different answers depending on
    # how recently the process restarted.
    settings = get_settings()
    if settings.public_market_collector_enabled:
        asyncio.create_task(run_market_engine())
    if settings.deriv_app_id:
        asyncio.create_task(run_otc_assets())


@app.on_event("shutdown")
async def _on_shutdown() -> None:
    stop_scheduler()
    # Hand power management back: a background process that leaves sleep
    # disabled forever is a bad neighbour.
    allow_sleep()
