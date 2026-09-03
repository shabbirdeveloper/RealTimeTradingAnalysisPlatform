"""
The broker-OTC poll cycle.

Deliberately a separate service from the public-market one rather than a
branch inside it. The two differ in almost everything that matters: where
bars come from (a websocket request against a broker versus a REST quote
vendor), how they are derived (sub-minute bars built from ticks versus
minute bars aggregated upward), what a stale bar means (three minutes
versus fifteen), and what may price them. A shared function with an
`is_otc` flag threaded through it would have to be read twice to answer
any question about either.

What they DO share is the part that must never diverge: the same
build_signal, the same outcome rule, the same storage, the same
provenance check. Those are imported, not reimplemented.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from app.features.signal_engine import build_signal
from app.instruments import deriv_api_symbol, get_instrument
from app.market_data.deriv_feed import (
    CANDLE_TIMEFRAMES,
    HISTORY_BARS,
    TICK_COUNT,
    TICK_TIMEFRAMES,
    DerivSyntheticFeed,
    ticks_to_candles,
)
from app.market_data.errors import MarketDataError
from app.storage.candle_repository import fetch_recent_otc_candles, upsert_otc_candles
from app.storage.signal_repository import insert_signal

logger = logging.getLogger(__name__)



async def collect_otc_symbol(symbol: str, feed: DerivSyntheticFeed) -> None:
    """One instrument, one cycle: fetch, store, decide, record.

    Raises nothing to the caller for ordinary market-data trouble -- an
    instrument that cannot be fetched is skipped with a warning, because
    one broker hiccup must not stop the others or abort resolution.
    """
    instrument = get_instrument(symbol)
    api_symbol = deriv_api_symbol(symbol)
    now = datetime.now(timezone.utc)

    stored: dict[str, int] = {}

    for timeframe in CANDLE_TIMEFRAMES:
        try:
            bars = await feed.fetch_bars(api_symbol, timeframe, HISTORY_BARS)
        except MarketDataError as exc:
            logger.warning("%s: %s bars unavailable: %s", symbol, timeframe, exc)
            continue
        stored[timeframe] = upsert_otc_candles(
            symbol, timeframe,
            [
                {"open_time": b.open_time, "open": b.open, "high": b.high,
                 "low": b.low, "close": b.close}
                for b in bars
            ],
            source=feed.name,
        )

    # Sub-minute bars, built from real ticks rather than interpolated from
    # minute bars. An interpolated 15-second bar would be invented data
    # wearing a real bar's shape, which is the one thing this project does
    # not do.
    try:
        ticks = await feed.fetch_ticks(api_symbol, count=TICK_COUNT)
    except MarketDataError as exc:
        logger.warning("%s: ticks unavailable, sub-minute bars skipped: %s", symbol, exc)
    else:
        for timeframe, seconds in TICK_TIMEFRAMES.items():
            built = ticks_to_candles(ticks, seconds, now=now)
            if built:
                stored[timeframe] = upsert_otc_candles(
                    symbol, timeframe, built[-HISTORY_BARS:], source=feed.name
                )

    if not stored:
        logger.warning("%s: nothing collected this cycle — no decision made", symbol)
        return

    logger.info(
        "%s: stored %s",
        symbol,
        ", ".join(f"{n} {tf}" for tf, n in stored.items()),
    )

    # Read back from storage rather than deciding on what was just fetched.
    # The engine must see exactly what a backtest of this moment would later
    # see; deciding on an in-memory list that storage might have rejected is
    # how live and replay quietly stop agreeing.
    history = {
        tf: fetch_recent_otc_candles(symbol, tf, HISTORY_BARS)
        for tf in instrument.profile.timeframes
    }

    decision = build_signal(symbol, history, now=now, feed=feed.descriptor)

    note = (decision.warnings or decision.reasons or ["-"])[0]
    logger.info(
        "%s: %s %s score=%d call=%d put=%d regime=%s%s | %s",
        symbol, decision.direction, decision.grade, decision.technical_score,
        decision.call_score, decision.put_score, decision.market_regime,
        f" expiry={decision.expiry_seconds}s" if decision.expiry_seconds else "",
        note[:110],
    )

    insert_signal(symbol, decision)


async def run_otc_cycle(symbols: list[str], app_id: str) -> None:
    """Every configured OTC instrument, isolated from one another."""
    feed = DerivSyntheticFeed(app_id)
    for symbol in symbols:
        try:
            await collect_otc_symbol(symbol, feed)
        except Exception:  # noqa: BLE001 -- one instrument must not stop the rest
            logger.exception("OTC cycle failed for %s — continuing", symbol)
