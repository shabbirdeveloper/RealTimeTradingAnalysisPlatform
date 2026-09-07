"""
The OTC collection and evaluation cycle (spec Phases 5, 12, 30).

One instrument, one cadence, one engine. Runs every 30 seconds so that
each closed S30 bar is evaluated exactly once -- Phase 12's cadence,
chosen because tick-level evaluation produces decisions that flip before
the bar they were computed from has even finished.

This module does I/O and nothing else. Every judgement belongs to
app.otc.engine.evaluate(), which has no clock and no network, so the
backtester can drive it over stored history and get provably identical
results. The moment a decision gets made here instead, replay stops being
a test of what production does.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from app.market_data.deriv_feed import (
    CANDLE_TIMEFRAMES,
    HISTORY_BARS,
    TICK_COUNT,
    TICK_TIMEFRAMES,
    DerivSyntheticFeed,
    ticks_to_candles,
)
from app.market_data.errors import MarketDataError
from app.otc.config import CONFIG, OTC_PROFILE, OTC_SYMBOLS, enabled_symbols
from app.otc.engine import evaluate
from app.otc.health import FeedStatus, MarketDataHealth, assess
from app.otc.repository import resolve_due_signals, store_decision

logger = logging.getLogger(__name__)


async def run_cycle(feed: DerivSyntheticFeed, now: datetime | None = None) -> None:
    """One pass over every enabled instrument, then resolution.

    Resolution runs even when collection failed: a signal that expired
    still deserves an honest outcome, and skipping it because the feed
    hiccuped would leave rows ACTIVE forever and quietly inflate the
    'pending' count instead of the loss count.
    """
    now = now or datetime.now(timezone.utc)

    for symbol in enabled_symbols():
        try:
            await collect_symbol(symbol, feed, now)
        except Exception:
            logger.exception("%s: cycle failed", symbol)

    try:
        count = resolve_due_signals(now)
        if count:
            logger.info("[OTC_RESULT] resolved %d expired signal(s)", count)
    except Exception:
        logger.exception("resolution pass failed")


async def collect_symbol(symbol: str, feed: DerivSyntheticFeed, now: datetime) -> None:
    cfg = OTC_SYMBOLS[symbol]
    api_symbol = cfg.api_symbol

    # --- ticks first: they are what health is judged on, and what the
    # sub-minute bars are built from.
    try:
        ticks = await feed.fetch_ticks(api_symbol, TICK_COUNT)
    except MarketDataError as exc:
        logger.warning("[OTC_FEED] %s: ticks unavailable: %s", symbol, exc)
        ticks = []

    health = _health_from_ticks(symbol, ticks, now)
    logger.info(
        "[OTC_FEED] %s %s (%s) %.1f ticks/min",
        symbol, health.status.value, health.reason, health.ticks_per_minute,
    )

    candles: dict[str, list[dict]] = {}

    # Sub-minute bars: nobody sells these, so they are ours to build.
    for timeframe, seconds in TICK_TIMEFRAMES.items():
        built = _validated(symbol, timeframe, ticks_to_candles(ticks, seconds, now=now))
        if built:
            candles[timeframe] = built[-HISTORY_BARS:]
            _upsert(symbol, timeframe, candles[timeframe], feed.name)

    # Minute-and-above bars come from the broker, because its own
    # aggregation is authoritative for its own series and our tick history
    # does not reach far enough back to rebuild M15.
    for timeframe in CANDLE_TIMEFRAMES:
        try:
            bars = await feed.fetch_bars(api_symbol, timeframe, HISTORY_BARS)
        except MarketDataError as exc:
            logger.warning("[OTC_CANDLE] %s: %s unavailable: %s", symbol, timeframe, exc)
            continue
        candles[timeframe] = [
            {
                "open_time": b.open_time, "open": b.open, "high": b.high,
                "low": b.low, "close": b.close,
            }
            for b in bars
        ]
        _upsert(symbol, timeframe, candles[timeframe], feed.name)

    logger.info(
        "[OTC_CANDLE] %s %s",
        symbol, " ".join(f"{tf}:{len(c)}" for tf, c in sorted(candles.items())),
    )

    decision = evaluate(symbol, candles, now, health, OTC_PROFILE)

    if decision.is_signal:
        logger.info(
            "[OTC_SIGNAL] %s %s @%.5f exp=%ds score=%d (call=%d put=%d) %s / %s",
            symbol, decision.direction.value, decision.price, decision.expiry_seconds,
            decision.score, decision.call_score, decision.put_score,
            decision.strategy, decision.regime,
        )
    else:
        logger.info(
            "[OTC_SCORE] %s NO_TRADE regime=%s (%s) call=%d put=%d — %s",
            symbol, decision.regime, decision.regime_reason or "no reason recorded",
            decision.call_score, decision.put_score,
            "; ".join(decision.rejection_reasons[:2]) or "no reason recorded",
        )

    store_decision(decision)


def _validated(symbol: str, timeframe: str, rows: list[dict]) -> list[dict]:
    """Drop bars whose own OHLC is self-contradictory before storing them.

    OTCBar refuses a bar whose open or close lies outside its high/low --
    exactly the corruption a bucketing bug produces. Running our tick-built
    candles through that constructor gets the same check the broker's bars
    already get; the validated rows are returned as dicts because that is
    what the storage layer takes.
    """
    from app.market_data.otc import OTCBar

    out: list[dict] = []
    for r in rows:
        try:
            OTCBar(
                symbol=symbol, open_time=r["open_time"], timeframe=timeframe,
                open=float(r["open"]), high=float(r["high"]), low=float(r["low"]),
                close=float(r["close"]), is_closed=True, source="tick_builder",
            )
        except ValueError as exc:
            logger.warning("[OTC_CANDLE] %s %s malformed bar dropped: %s", symbol, timeframe, exc)
            continue
        out.append(r)
    return out


def _upsert(symbol: str, timeframe: str, rows: list[dict], source: str) -> None:
    """Persist bars. The storage import is deferred so that this module --
    and the health derivation below it -- can be imported and tested
    without pydantic or database credentials present."""
    from app.storage.candle_repository import upsert_otc_candles

    if not rows:
        return
    try:
        upsert_otc_candles(symbol, timeframe, rows, source=source)
    except Exception as exc:
        logger.warning("[OTC_CANDLE] %s: %s storage failed: %s", symbol, timeframe, exc)


def _health_from_ticks(symbol: str, ticks: list, now: datetime) -> MarketDataHealth:
    """Derive Phase 7's health from what actually arrived.

    Duplicates are counted rather than silently dropped: a feed repeating
    the same timestamped price is not the same as a feed that is simply
    quiet, and only one of those is a problem worth waking someone for.
    """
    if not ticks:
        return assess(symbol, last_tick_at=None, ticks_per_minute=0.0, now=now)

    timestamps = [t for t, _ in ticks]
    span = (timestamps[-1] - timestamps[0]).total_seconds()
    rate = len(ticks) / (span / 60.0) if span > 0 else 0.0
    duplicates = sum(1 for a, b in zip(ticks, ticks[1:]) if a == b)

    return assess(
        symbol,
        last_tick_at=timestamps[-1],
        ticks_per_minute=rate,
        duplicate_ticks=duplicates,
        now=now,
    )
