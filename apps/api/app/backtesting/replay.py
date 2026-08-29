"""
Point-in-time history slicing -- the single most correctness-critical
piece of the backtester (spec section 13: "Do NOT use look-ahead bias.
Do NOT use future data in feature calculation.").

The whole no-look-ahead guarantee reduces to one rule, enforced here in
one place so it cannot be quietly violated somewhere else:

    At simulated time T, the only candles that exist are the ones that
    had already CLOSED at T.

A candle is identified by its `open_time`, but it isn't knowable until
its window ends -- an H4 candle opening at 12:00 tells you nothing at
13:00, because at 13:00 its high/low/close haven't happened yet. Using
it would leak up to 4 hours of future price into a decision. So the
filter is on `open_time + timeframe_duration <= as_of`, never on
`open_time <= as_of`.

Pure functions, no I/O, no dependencies -- so this is directly unit
testable, and `tests/test_replay.py` includes a regression test that
injects a violent future price spike and asserts an earlier decision is
bit-for-bit unchanged.
"""
from __future__ import annotations

from datetime import datetime, timedelta

TIMEFRAME_MINUTES: dict[str, int] = {"M5": 5, "M15": 15, "H1": 60, "H4": 240}


class ReplayError(ValueError):
    """Raised on misuse -- an unknown timeframe, or naive datetimes."""


def _require_aware(dt: datetime, label: str) -> None:
    if dt.tzinfo is None:
        raise ReplayError(f"{label} must be timezone-aware (UTC); got a naive datetime")


def candle_close_time(candle: dict, timeframe: str) -> datetime:
    """The moment this candle's window ends -- i.e. the earliest time its
    OHLC values could actually be known."""
    minutes = TIMEFRAME_MINUTES.get(timeframe)
    if minutes is None:
        raise ReplayError(f"unknown timeframe {timeframe!r}")
    open_time = candle["open_time"]
    _require_aware(open_time, "candle open_time")
    return open_time + timedelta(minutes=minutes)


def candles_closed_by(candles: list[dict], timeframe: str, as_of: datetime) -> list[dict]:
    """Only the candles fully closed at `as_of`, oldest-first.

    `candles` must be oldest-first. Returns a new list; never mutates the
    input, so the caller can hold one immutable full-history list and
    slice it repeatedly across the whole replay.
    """
    _require_aware(as_of, "as_of")
    if timeframe not in TIMEFRAME_MINUTES:
        raise ReplayError(f"unknown timeframe {timeframe!r}")
    return [c for c in candles if candle_close_time(c, timeframe) <= as_of]


def slice_history(
    candles_by_timeframe: dict[str, list[dict]], as_of: datetime
) -> dict[str, list[dict]]:
    """Applies `candles_closed_by` across every timeframe at once -- the
    exact input shape `app.features.signal_engine.build_signal` expects,
    but containing only what was knowable at `as_of`."""
    return {
        timeframe: candles_closed_by(candles, timeframe, as_of)
        for timeframe, candles in candles_by_timeframe.items()
    }


def first_candle_at_or_after(candles: list[dict], at: datetime) -> dict | None:
    """The earliest candle opening at/after `at`. Used to price a signal's
    outcome at expiry. Returns None when history simply doesn't reach that
    far -- the caller must then leave the signal unresolved rather than
    invent a closing price."""
    _require_aware(at, "at")
    for candle in candles:
        if candle["open_time"] >= at:
            return candle
    return None
