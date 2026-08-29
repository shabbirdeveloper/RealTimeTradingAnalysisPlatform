"""
One poll cycle: fetch the latest M5 candles for an asset, store them,
derive M15/H1/H4 from stored history, store those, and report health.
Called by the scheduler on each tick; also callable directly (a one-off
script, a manual trigger, a test) without needing APScheduler at all.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

from app.aggregation import Candle as AggCandle
from app.aggregation import Timeframe as AggTimeframe
from app.aggregation import aggregate_candles
from app.market_data.base import MarketDataError, MarketDataProvider
from app.schemas.candle import Asset, Candle, Timeframe
from app.storage.candle_repository import fetch_recent_candles, upsert_candles
from app.storage.health_repository import report_component_health

logger = logging.getLogger(__name__)

# M5 bars kept in memory for deriving H4 candles (48 M5 bars per H4
# bucket); fetched with extra headroom so a couple of closed H4 buckets
# are always derivable, not just the newest one.
_M5_LOOKBACK_FOR_H4 = 48 * 3


def _to_agg_candle(c: Candle) -> AggCandle:
    return AggCandle(
        open_time=c.open_time, open=c.open, high=c.high, low=c.low, close=c.close, volume=c.volume
    )


def _from_agg_candle(c: AggCandle) -> Candle:
    return Candle(
        open_time=c.open_time, open=c.open, high=c.high, low=c.low, close=c.close, volume=c.volume
    )


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
