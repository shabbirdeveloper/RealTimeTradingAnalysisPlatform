"""
One poll cycle: fetch the latest M5 candles for an asset, store them,
derive M15/H1/H4 from stored history, store those, compute real technical
features + a real signal decision from stored history, store both, and
report health. Called by the scheduler on each tick; also callable
directly (a one-off script, a manual trigger, a test) without needing
APScheduler at all.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

from app.aggregation import Candle as AggCandle
from app.aggregation import Timeframe as AggTimeframe
from app.aggregation import aggregate_candles
from app.features.signal_engine import build_signal
from app.features.snapshot import compute_feature_dict
from app.market_data.base import MarketDataError, MarketDataProvider
from app.news.factory import build_calendar_provider
from app.schemas.candle import Asset, Candle, Timeframe
from app.storage import audit_repository as audit
from app.storage.candle_repository import fetch_recent_candles, upsert_candles
from app.storage.event_repository import fetch_events_near
from app.storage.feature_repository import upsert_features
from app.storage.health_repository import report_component_health
from app.storage.signal_repository import insert_signal

logger = logging.getLogger(__name__)

# M5 bars kept in memory for deriving H4 candles (48 M5 bars per H4
# bucket); fetched with extra headroom so a couple of closed H4 buckets
# are always derivable, not just the newest one.
_M5_LOOKBACK_FOR_H4 = 48 * 3

# History fetched per timeframe for the feature/signal engine. 250 covers
# a real EMA200 once that much real history exists; fewer real candles
# just means the feature engine honestly reports "insufficient data"
# until then -- see app/features/timeframe_bias.py.
_FEATURE_LOOKBACK = 250


def _to_agg_candle(c: Candle) -> AggCandle:
    return AggCandle(
        open_time=c.open_time, open=c.open, high=c.high, low=c.low, close=c.close, volume=c.volume
    )


def _from_agg_candle(c: AggCandle) -> Candle:
    return Candle(
        open_time=c.open_time, open=c.open, high=c.high, low=c.low, close=c.close, volume=c.volume
    )


def _to_feature_dict(c: Candle) -> dict:
    return {
        "open": float(c.open),
        "high": float(c.high),
        "low": float(c.low),
        "close": float(c.close),
        "open_time": c.open_time,
    }


async def run_poll_cycle(
    asset: Asset, provider: MarketDataProvider, *, poll_outputsize: int
) -> None:
    started = time.monotonic()
    component = f"market_data.{asset.value}"

    try:
        fresh_m5 = await provider.fetch_latest_m5(asset, poll_outputsize)
    except MarketDataError as exc:
        logger.warning("market data fetch failed for %s via %s: %s", asset.value, provider.name, exc)
        report_component_health(component, status="Warning", details={"provider": provider.name, "error": str(exc)})
        audit.record(
            audit.ACTION_MARKET_DATA_FAILED,
            target_table="candles",
            target_id=asset.value,
            metadata={"provider": provider.name, "error": str(exc)},
        )
        return

    if not fresh_m5:
        logger.warning("provider %s returned zero candles for %s", provider.name, asset.value)
        report_component_health(
            component, status="Warning", details={"provider": provider.name, "error": "empty response"}
        )
        return

    upsert_candles(asset, Timeframe.M5, fresh_m5, source=provider.name)

    # Pull recent M5 history from storage (not just this poll's batch) so
    # H4 aggregation -- 48 M5 bars per bucket -- has enough to work with
    # even right after a restart.
    history = fetch_recent_candles(asset, Timeframe.M5, _M5_LOOKBACK_FOR_H4)
    agg_source = [_to_agg_candle(c) for c in (history or fresh_m5)]

    now = datetime.now(timezone.utc)
    for target, agg_target in (
        (Timeframe.M15, AggTimeframe.M15),
        (Timeframe.H1, AggTimeframe.H1),
        (Timeframe.H4, AggTimeframe.H4),
    ):
        derived = aggregate_candles(agg_source, AggTimeframe.M5, agg_target, now=now)
        if derived:
            upsert_candles(
                asset, target, [_from_agg_candle(c) for c in derived], source=f"{provider.name}+aggregated"
            )

    latency_ms = round((time.monotonic() - started) * 1000)
    report_component_health(
        component,
        status="Healthy",
        details={
            "provider": provider.name,
            "last_candle_time": fresh_m5[-1].open_time.isoformat(),
            "latency_ms": latency_ms,
        },
    )

    _run_analysis_cycle(asset)


def _run_analysis_cycle(asset: Asset) -> None:
    """Real technical analysis + signal decision from real stored candle
    history (spec sections 6-12), with the news filter applied (section 8).
    Failures here are logged and swallowed -- a feature/signal computation
    problem should never take down candle collection, which is the more
    critical half of this poll cycle.
    """
    try:
        candles_by_timeframe: dict[str, list[dict]] = {}
        for tf in (Timeframe.H4, Timeframe.H1, Timeframe.M15, Timeframe.M5):
            stored = fetch_recent_candles(asset, tf, _FEATURE_LOOKBACK)
            feature_candles = [_to_feature_dict(c) for c in stored]
            candles_by_timeframe[tf.value] = feature_candles
            if feature_candles:
                upsert_features(asset, tf, feature_candles[-1]["open_time"], compute_feature_dict(feature_candles))

        now = datetime.now(timezone.utc)

        # News protection. `calendar_available` tracks whether a real feed
        # is configured -- an empty event list from an unconfigured
        # provider must NOT be read as "nothing scheduled, all clear".
        calendar_provider = build_calendar_provider()
        calendar_available = calendar_provider.is_configured
        events = fetch_events_near(now) if calendar_available else []

        decision = build_signal(
            asset.value,
            candles_by_timeframe,
            now=now,
            economic_events=events,
            calendar_available=calendar_available,
        )
        insert_signal(asset, decision)
    except Exception as exc:  # noqa: BLE001 -- deliberately broad, see docstring
        logger.exception("analysis cycle failed for %s", asset.value)
        audit.record(
            audit.ACTION_ANALYSIS_FAILED,
            target_table="signals",
            target_id=asset.value,
            metadata={"error": str(exc)},
        )
