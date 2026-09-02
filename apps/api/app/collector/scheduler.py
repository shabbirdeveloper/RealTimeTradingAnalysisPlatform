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
import time

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.collector.market_hours import any_market_open, is_market_open
from app.collector.resolution import resolve_expired_signals, resolve_shadow_opportunities
from app.collector.service import run_poll_cycle
from app.config import get_settings
from app.market_data.base import MarketDataProvider
from app.market_data.demo_provider import DemoMarketDataProvider
from app.market_data.twelve_data_provider import TwelveDataProvider
from app.notifications.heartbeat import send_heartbeat
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
    if not force and not any_market_open():
        logger.info("all markets closed -- skipping poll cycle")
        return
    if not settings.has_supabase:
        logger.warning("SUPABASE_URL/SUPABASE_SERVICE_ROLE_KEY not set -- skipping poll cycle")
        return

    # A cycle that succeeds used to log NOTHING. The console then sat silent
    # for the whole poll interval, which is indistinguishable from a hung
    # process -- and a collector that looks hung gets killed. Silence is a
    # terrible way to report "working".
    started = time.monotonic()
    logger.info("---- poll cycle starting ----")

    provider = build_provider()
    for asset in Asset:
        # Per-asset, not per-cycle: crypto trades through the weekend while
        # forex/gold are shut. A single global check would either blind the
        # crypto pairs on Saturday or burn API credits re-fetching identical
        # closed-market forex candles.
        if not force and not is_market_open(asset):
            logger.debug("%s market closed -- skipping", asset.value)
            continue
        try:
            await run_poll_cycle(asset, provider, poll_outputsize=settings.poll_outputsize)
        except Exception:  # noqa: BLE001 -- deliberately broad, see below
            # run_poll_cycle handles MarketDataError itself. Anything reaching
            # here is unexpected -- a bug, a storage failure, a provider
            # returning a shape nobody anticipated. Without this guard it
            # aborted the whole loop: every asset after this one was skipped
            # AND, worse, signal resolution below never ran. Signals would sit
            # ACTIVE past their expiry and accuracy would silently stop being
            # measured -- a failure that looks like "no results yet" rather
            # than like an error.
            #
            # (This is not hypothetical: a KeyError in the demo provider's
            # per-asset volatility map did exactly this for anyone running
            # without an API key.)
            logger.exception("poll cycle crashed for %s -- continuing with other assets", asset.value)

    elapsed = time.monotonic() - started
    logger.info(
        "---- poll cycle done in %.1fs; next in ~%ds ----",
        elapsed, settings.poll_interval_seconds,
    )

    # Signal resolution (spec section 49) -- checks real candles against
    # any ACTIVE signal whose expiry has passed. Reads already-stored
    # data only, no provider calls, so it's safe and cheap to run every
    # cycle regardless of how many (if any) new candles just came in.
    try:
        resolve_expired_signals()
    except Exception:  # noqa: BLE001 -- a resolution failure must never block candle collection
        logger.exception("signal resolution failed")

    # Counterfactual scoring of REJECTED setups. Isolated in its own try so a
    # failure here can affect neither candle collection nor real resolution --
    # this is analysis data, strictly less important than either.
    try:
        resolve_shadow_opportunities()
    except Exception:  # noqa: BLE001
        logger.exception("shadow resolution failed")


async def run_daily_heartbeat() -> None:
    """Sends the daily "collector is alive" report.

    Wrapped whole: a notification failure must never look like, or become,
    a collection failure. The report is a convenience; the candles are not.
    """
    try:
        send_heartbeat()
    except Exception:  # noqa: BLE001 -- reporting must not affect collection
        logger.exception("daily heartbeat failed")


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
    if settings.heartbeat_enabled:
        _scheduler.add_job(
            run_daily_heartbeat,
            "cron",
            hour=settings.heartbeat_hour_utc,
            minute=0,
            id="daily_heartbeat",
            max_instances=1,
            coalesce=True,
        )
        logger.info("daily heartbeat scheduled for %02d:00 UTC", settings.heartbeat_hour_utc)
    elif settings.has_telegram:
        logger.info("daily heartbeat disabled (HEARTBEAT_HOUR_UTC=-1)")

    _scheduler.start()
    logger.info("market data scheduler started (interval=%ss)", settings.poll_interval_seconds)
    return _scheduler


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
