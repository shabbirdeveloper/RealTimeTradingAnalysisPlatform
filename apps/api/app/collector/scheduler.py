"""
Background polling loop. Uses APScheduler's AsyncIOScheduler so it runs
inside the same event loop as the FastAPI app -- no separate process or
thread needed for this phase's scope. For the eventual AWS/VPS/Docker
deployment (spec section: "Trading/signal engine: AWS/VPS/Docker"), this
whole app can just run as a long-lived container; nothing here assumes a
serverless/short-lived environment.
"""

from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.collector.market_hours import is_market_open
from app.collector.resolution import resolve_expired_signals
from app.collector.service import run_poll_cycle
from app.config import get_settings
from app.market_data.base import MarketDataProvider
from app.market_data.demo_provider import DemoMarketDataProvider
from app.market_data.twelve_data_provider import TwelveDataProvider
from app.schemas.candle import Asset

logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None


def build_provider() -> MarketDataProvider:
    settings = get_settings()
    if settings.has_real_provider:
        return TwelveDataProvider(settings.twelve_data_api_key)
    logger.warning(
        "TWELVE_DATA_API_KEY not set -- collector is running against the "
        "DEMO provider. No real candles will be stored. Set the key in "
        "apps/api/.env to switch to live data."
    )
    return DemoMarketDataProvider()


async def run_all_assets(*, force: bool = False) -> None:
    """Runs one poll cycle for every configured asset.

    `force=True` skips the market-hours check -- used by the manual
    /debug/poll-now endpoint so the pipeline can be tested any time,
    including on a closed weekend market. The regular scheduled job never
    passes force=True, so it still respects market hours and the normal
    API-credit budget.
    """
    settings = get_settings()
    if not force and not is_market_open():
        logger.info("market closed (weekend) -- skipping poll cycle")
        return
    if not settings.has_supabase:
        logger.warning("SUPABASE_URL/SUPABASE_SERVICE_ROLE_KEY not set -- skipping poll cycle")
        return

    provider = build_provider()
    for asset in Asset:
        await run_poll_cycle(asset, provider, poll_outputsize=settings.poll_outputsize)

    # Signal resolution (spec section 49) -- checks real candles against
    # any ACTIVE signal whose expiry has passed. Reads already-stored
    # data only, no provider calls, so it's safe and cheap to run every
    # cycle regardless of how many (if any) new candles just came in.
    try:
        resolve_expired_signals()
    except Exception:  # noqa: BLE001 -- a resolution failure must never block candle collection
        logger.exception("signal resolution failed")


def start_scheduler() -> AsyncIOScheduler:
    global _scheduler
    settings = get_settings()
    _scheduler = AsyncIOScheduler(timezone="UTC")
    _scheduler.add_job(
        run_all_assets,
        "interval",
        seconds=settings.poll_interval_seconds,
        id="market_data_poll",
        max_instances=1,
        coalesce=True,
    )
    _scheduler.start()
    logger.info("market data scheduler started (interval=%ss)", settings.poll_interval_seconds)
    return _scheduler


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
