"""
The 5-minute engine on real-market instruments (spec Phase 1, extended).

Same engine, same three strategies, same 300-second expiry as the broker
feed — only the data source and the timeframe profile differ. Deliberately
NOT a second engine: two implementations of the same idea drift, and the
drift is invisible until their accuracy figures disagree and nobody can
say why.

WHY M1 IS FETCHED INSTEAD OF M5
-------------------------------
The engine needs M1 as both its confirmation and its entry timeframe, and
M3 for momentum. Neither can be built from M5 — a three-minute bar is not
a whole number of five-minute bars, and a one-minute bar certainly is not.
So M1 is fetched and M3/M5/M15 are aggregated upward from it, which keeps
the cost at ONE provider request per asset per cycle. That is the number
the free tier's 800/day budget is built on, and doubling it would exhaust
the quota before noon.

WHY THE FEED IS TREATED AS HEALTHY WHEN BARS ARE FRESH
------------------------------------------------------
A quote vendor publishes no ticks, so tick-rate health cannot be measured
the way it is for the broker feed. Freshness of the newest CLOSED bar is
the honest substitute, and it is reported as exactly that rather than
being dressed up as a tick rate the provider never gave us.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from app.aggregation import Candle as AggCandle
from app.aggregation import Timeframe as AggTimeframe
from app.aggregation import aggregate_candles
from app.collector.market_hours import is_market_open
from app.market_data.base import MarketDataProvider
from app.market_data.closed_bars import split_closed
from app.market_data.errors import MarketDataError
from app.otc.config import REAL_MARKET_PROFILE
from app.otc.engine import evaluate
from app.otc.health import FeedStatus, MarketDataHealth
from app.otc.repository import store_decision

logger = logging.getLogger(__name__)

# One request returns this many M1 bars. 900 minutes is fifteen hours, which
# aggregates to 60 M15 bars — exactly the engine's warm-up requirement — so
# a cold start is productive from its first cycle instead of after a day.
M1_OUTPUTSIZE = 900

# Derived from the M1 bars, never fetched.
DERIVED: tuple[tuple[str, AggTimeframe], ...] = (
    ("M3", AggTimeframe.M3),
    ("M5", AggTimeframe.M5),
    ("M15", AggTimeframe.M15),
)

# A closed M1 bar older than this means the feed has fallen behind. Three
# minutes rather than one: a vendor that publishes a minute late is normal,
# a vendor three minutes late is not, and the 300-second expiry cannot
# absorb more than that.
MAX_BAR_AGE_SECONDS = 180


async def collect_market_symbol(
    symbol: str, provider: MarketDataProvider, now: datetime
) -> None:
    """One real-market instrument, one cycle."""
    from app.schemas.candle import Asset

    try:
        asset = Asset(symbol)
    except ValueError:
        logger.warning("[MKT_FEED] %s is not a public-market instrument", symbol)
        return

    if not is_market_open(symbol, now):
        logger.info("[MKT_FEED] %s market closed — no evaluation", symbol)
        return

    try:
        raw = await provider.fetch_latest_m1(asset, M1_OUTPUTSIZE)
    except MarketDataError as exc:
        logger.warning("[MKT_FEED] %s M1 unavailable: %s", symbol, exc)
        return

    # Only bars that had CLOSED at `now`. The forming bar is still moving,
    # and including it makes every indicator disagree with what the same
    # code would compute in replay.
    split = split_closed(raw, "M1", now)
    closed = list(split.closed)
    if not closed:
        logger.warning("[MKT_FEED] %s returned no closed M1 bars", symbol)
        return

    candles: dict[str, list[dict]] = {"M1": [_as_dict(c) for c in closed]}

    source = [
        AggCandle(open_time=c.open_time, open=c.open, high=c.high, low=c.low, close=c.close)
        for c in closed
    ]
    for name, target in DERIVED:
        try:
            derived = aggregate_candles(source, AggTimeframe.M1, target, now=now)
        except Exception as exc:  # noqa: BLE001
            logger.warning("[MKT_CANDLE] %s %s aggregation failed: %s", symbol, name, exc)
            continue
        if derived:
            candles[name] = [_as_dict(c) for c in derived]

    health = _health_from_bars(symbol, closed[-1].open_time, len(closed), now)
    logger.info(
        "[MKT_CANDLE] %s %s | feed %s (%s)",
        symbol,
        " ".join(f"{tf}:{len(rows)}" for tf, rows in sorted(candles.items())),
        health.status.value, health.reason,
    )

    decision = evaluate(symbol, candles, now, health, REAL_MARKET_PROFILE)

    if decision.is_signal:
        logger.info(
            "[MKT_SIGNAL] %s %s @%.5f exp=%ds score=%d (call=%d put=%d) %s / %s",
            symbol, decision.direction.value, decision.price, decision.expiry_seconds,
            decision.score, decision.call_score, decision.put_score,
            decision.strategy, decision.regime,
        )
    else:
        logger.info(
            "[MKT_SCORE] %s NO_TRADE regime=%s (%s) call=%d put=%d — %s",
            symbol, decision.regime, decision.regime_reason or "no reason recorded",
            decision.call_score, decision.put_score,
            "; ".join(decision.rejection_reasons[:2]) or "no reason recorded",
        )

    store_decision(decision)


def _as_dict(candle) -> dict:
    return {
        "open_time": candle.open_time,
        "open": float(candle.open),
        "high": float(candle.high),
        "low": float(candle.low),
        "close": float(candle.close),
    }


def _health_from_bars(
    symbol: str, newest_bar: datetime, bar_count: int, now: datetime
) -> MarketDataHealth:
    """Bar freshness stands in for tick rate, and says so.

    ticks_per_minute is reported as 0.0 because a quote vendor gives us no
    ticks — not as an invented figure. A zero that means "not measurable
    here" is honest; a fabricated 30.0 would make the health record look
    identical to the broker feed's and hide which source a decision came
    from.
    """
    age = (now - newest_bar).total_seconds()
    if age > MAX_BAR_AGE_SECONDS * 4:
        status, reason = FeedStatus.DISCONNECTED, f"newest closed M1 bar is {age/60:.0f} min old"
    elif age > MAX_BAR_AGE_SECONDS:
        status, reason = FeedStatus.STALE, f"newest closed M1 bar is {age:.0f}s old"
    elif bar_count < 100:
        status, reason = FeedStatus.DEGRADED, f"only {bar_count} closed M1 bars available"
    else:
        status, reason = FeedStatus.HEALTHY, f"{bar_count} closed M1 bars, newest {age:.0f}s old"

    return MarketDataHealth(
        symbol=symbol, status=status, last_tick_at=newest_bar,
        latency_ms=None, ticks_per_minute=0.0,
        duplicate_ticks=0, rejected_ticks=0, reason=reason,
    )
