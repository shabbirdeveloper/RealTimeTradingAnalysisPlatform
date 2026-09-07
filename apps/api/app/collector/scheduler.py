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
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.collector.cadence import (
    TICK_SECONDS,
    daily_request_estimate,
    interval_seconds,
    should_poll,
)
from app.collector.market_hours import any_market_open, is_market_open
from app.collector.resolution import resolve_expired_signals, resolve_shadow_opportunities
from app.otc.collector import run_cycle as run_otc_cycle
from app.otc.config import CONFIG, REAL_MARKET_PROFILE, TIMEFRAME_SECONDS, enabled_symbols
from app.otc.market_collector import collect_market_symbol
from app.collector.service import run_poll_cycle
from app.config import get_settings
from app.market_data.base import MarketDataProvider
from app.market_data.demo_provider import DemoMarketDataProvider
from app.market_data.twelve_data_provider import TwelveDataProvider
from app.notifications.heartbeat import send_heartbeat
from app.schemas.candle import Asset

logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None

# When each asset was last polled, for the per-asset cadence. In memory
# on purpose: after a restart every asset is due immediately, which is
# the behaviour you want -- a restart should refresh, not wait.
_last_polled: dict[str, datetime] = {}


# Phase 12's evaluation cadence. Named rather than inline so the scheduler
# and the engine's own config cannot drift apart unnoticed.
OTC_TICK_SECONDS = TIMEFRAME_SECONDS[CONFIG.evaluation_timeframe]


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
    polled: list[str] = []
    skipped: dict[str, str] = {}
    for asset in Asset:
        # Per-asset, not per-cycle: crypto trades through the weekend while
        # forex/gold are shut. A single global check would either blind the
        # crypto pairs on Saturday or burn API credits re-fetching identical
        # closed-market forex candles.
        if not force and not is_market_open(asset):
            skipped[asset.value] = "market closed"
            continue

        # Per-asset cadence (see collector/cadence.py). One global interval
        # would have to be fast enough for London and cheap enough for a
        # dead Asian session at the same time, and the provider's daily cap
        # does not degrade gracefully when you guess wrong.
        now = datetime.now(timezone.utc)
        if not force and not should_poll(asset.value, now, _last_polled.get(asset.value)):
            skipped[asset.value] = f"not due (every {interval_seconds(asset.value, now)}s)"
            continue
        _last_polled[asset.value] = now
        polled.append(asset.value)

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
    # A cycle that polled nothing used to print "done in 0.0s" and stop,
    # which is indistinguishable from a cycle that worked. Every asset was
    # skipped for a reason, and the reasons are the only interesting thing
    # about such a cycle -- so say them, at INFO, where someone reading the
    # console will actually see them.
    if not polled:
        logger.info(
            "---- poll cycle polled NOTHING: %s ----",
            "; ".join(f"{a} ({why})" for a, why in skipped.items()) or "no assets configured",
        )
    else:
        logger.info(
            "---- poll cycle done in %.1fs; polled %s%s; next in ~%ds ----",
            elapsed, ", ".join(polled),
            f"; skipped {len(skipped)}" if skipped else "",
            settings.poll_interval_seconds,
        )


async def run_market_engine() -> None:
    """The 5-minute engine over every real-market instrument.

    Wrapped per asset: one instrument whose quote request fails must not
    stop the other four, because a single provider hiccup should cost one
    evaluation rather than the whole cycle.

    Records a heartbeat whatever happens. A cycle that ran and declined
    everything, and a cycle that never ran at all, are indistinguishable
    from the decisions table -- both leave it unchanged -- and they need
    opposite responses. The heartbeat is what separates them, so it is
    written even when the cycle fails.
    """
    settings = get_settings()
    if not settings.has_supabase:
        logger.warning("SUPABASE not configured -- skipping market engine cycle")
        return

    if not settings.has_real_provider:
        # Distinct from a feed hiccup, and it must not read as one. The
        # demo provider publishes no one-minute bars, so EVERY asset fails
        # identically and forever -- five warnings a cycle that look
        # transient but never clear.
        logger.error(
            "TWELVE_DATA_API_KEY is not set. The 5-minute engine needs real "
            "one-minute candles and the demo provider has none, so NO real-market "
            "decision can be produced until the key is set in apps/api/.env."
        )
        _heartbeat("Signal Engine (real market)", "Offline",
                   {"reason": "TWELVE_DATA_API_KEY not set", "evaluated": 0})
        return

    try:
        provider = build_provider()
    except Exception as exc:  # noqa: BLE001
        logger.exception("no market-data provider available")
        _heartbeat("Signal Engine (real market)", "Offline", {"reason": str(exc)[:200]})
        return

    now = datetime.now(timezone.utc)
    evaluated, failed = 0, 0
    for asset in Asset:
        try:
            await collect_market_symbol(asset.value, provider, now)
            evaluated += 1
        except Exception:  # noqa: BLE001
            failed += 1
            logger.exception("%s: market engine cycle failed", asset.value)

    _heartbeat(
        "Signal Engine (real market)",
        "Healthy" if failed == 0 else ("Warning" if evaluated else "Offline"),
        {"evaluated": evaluated, "failed": failed, "interval_seconds": REAL_MARKET_PROFILE.evaluation_seconds},
    )


def _heartbeat(component: str, status: str, details: dict) -> None:
    """Best-effort. A failed heartbeat must never take down the cycle it is
    only describing."""
    try:
        from app.storage.health_repository import report_component_health

        report_component_health(component, status=status, details=details)
    except Exception:  # noqa: BLE001
        logger.debug("heartbeat write failed for %s", component, exc_info=True)


async def run_resolution() -> None:
    """Score signals whose expiry has passed (spec section 49).

    Its OWN job, not a tail-call at the end of a collector.

    It used to run inside run_all_assets, which meant switching the
    public-market collector off silently switched off resolution for
    everything -- every expired signal simply stayed ACTIVE, and a growing
    backlog of unresolved rows reads exactly like a quiet market rather
    than a broken one.

    Resolution is not collection. It makes no provider calls, reads only
    stored data, and matters just as much when nothing is being collected:
    an expired signal deserves an honest outcome regardless of what the
    feeds are doing.
    """
    settings = get_settings()
    if not settings.has_supabase:
        return
    try:
        resolve_expired_signals()
    except Exception:  # noqa: BLE001
        logger.exception("signal resolution failed")

    # Counterfactual scoring of REJECTED setups. Isolated so a failure here
    # can affect neither collection nor real resolution -- this is analysis
    # data, strictly less important than either.
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


async def run_otc_assets() -> None:
    """The OTC cycle (app.otc), on its own schedule.

    Separate from the public-market job because the two have nothing in
    common operationally. OTC instruments never close, so there are no
    market hours to respect; the horizon is five minutes rather than
    fifteen; and the budget is a different provider's.

    Wrapped whole: an OTC failure must not touch public-market collection
    or signal resolution, which is what a shared job would risk.
    """
    from app.market_data.deriv_feed import DerivSyntheticFeed

    settings = get_settings()
    if not settings.deriv_app_id:
        return
    if not settings.has_supabase:
        logger.warning("SUPABASE not configured -- skipping OTC cycle")
        return
    try:
        await run_otc_cycle(DerivSyntheticFeed(settings.deriv_app_id))
        _heartbeat("Signal Engine (broker OTC)", "Healthy",
                   {"symbols": enabled_symbols(), "interval_seconds": OTC_TICK_SECONDS})
    except Exception as exc:  # noqa: BLE001
        logger.exception("OTC cycle failed")
        _heartbeat("Signal Engine (broker OTC)", "Offline", {"reason": str(exc)[:200]})


def start_scheduler() -> AsyncIOScheduler:
    global _scheduler
    settings = get_settings()
    _scheduler = AsyncIOScheduler(timezone="UTC")
    tick = TICK_SECONDS if settings.adaptive_polling else settings.poll_interval_seconds
    if settings.public_market_collector_enabled:
        # The SAME 5-minute engine as the broker feed, on the real pairs.
        # Every five minutes, which is both the provider's practical budget
        # and the rate at which the M1 entry bar meaningfully changes.
        _scheduler.add_job(
            run_market_engine,
            "interval",
            seconds=REAL_MARKET_PROFILE.evaluation_seconds,
            id="market_engine",
            max_instances=1,
            coalesce=True,
        )
        logger.info(
            "5-minute engine started (every %ss) for %s",
            REAL_MARKET_PROFILE.evaluation_seconds,
            ", ".join(a.value for a in Asset),
        )
    else:
        logger.info(
            "real-market engine disabled -- the broker-OTC engine is the only "
            "engine running (PUBLIC_MARKET_COLLECTOR_ENABLED=true to re-enable)"
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

    # Resolution runs on its own schedule, always. Every minute, because
    # the shortest expiry is 300s and a signal that expired should not wait
    # long for an honest answer.
    if settings.has_supabase:
        _scheduler.add_job(
            run_resolution,
            "interval",
            seconds=60,
            id="signal_resolution",
            max_instances=1,
            coalesce=True,
        )

    if settings.deriv_app_id:
        # Every 30 seconds, so each closed S30 bar is evaluated exactly
        # once (spec Phase 12). Evaluating per tick instead produces
        # decisions that flip before the bar they were computed from has
        # finished forming; evaluating less often means the entry-timing
        # check reads a bar that is already history.
        #
        # coalesce + max_instances=1 matter here: a slow cycle must be
        # skipped, never queued. A backlog of 30-second jobs would evaluate
        # stale markets at speed and store every one of them.
        _scheduler.add_job(
            run_otc_assets,
            "interval",
            seconds=OTC_TICK_SECONDS,
            id="otc_poll",
            max_instances=1,
            coalesce=True,
        )
        logger.info(
            "OTC engine started (every %ss) for %s",
            OTC_TICK_SECONDS, ", ".join(enabled_symbols()) or "(none enabled)",
        )

    _scheduler.start()
    # Only report the public-market cadence when that job actually exists.
    # Logging "scheduler started" for a job that was never added is the
    # same class of error as a stale price shown as live: the line reads
    # as a statement about the world and is not one.
    if settings.public_market_collector_enabled:
        if settings.adaptive_polling:
            symbols = [a.value for a in Asset]
            logger.info(
                "market data scheduler started (tick=%ss, per-asset cadence; "
                "~%.0f provider requests/day at this configuration)",
                tick, daily_request_estimate(symbols),
            )
        else:
            logger.info("market data scheduler started (fixed interval=%ss)", tick)
    return _scheduler


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
