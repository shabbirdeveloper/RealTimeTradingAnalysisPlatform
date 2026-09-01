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

# Durations in SECONDS, not minutes.
#
# Quotex OTC is traded on 15-second to 1-minute horizons, and an integer
# minute cannot express 15 seconds. Every duration table in the codebase was
# integer minutes, which made sub-minute analysis unrepresentable rather than
# merely unimplemented -- the kind of constraint that gets discovered halfway
# through building on top of it.
#
# One table, shared by the backtester, the ingestion filter and the
# aggregator, because two definitions of "how long is a bar" that drift apart
# is exactly the class of bug the closed-bar work exists to prevent.
TIMEFRAME_SECONDS: dict[str, int] = {
    "S15": 15,
    "S30": 30,
    "M1": 60,
    "M3": 180,
    "M5": 300,
    "M15": 900,
    "H1": 3600,
    "H4": 14400,
}


class ReplayError(ValueError):
    """Raised on misuse -- an unknown timeframe, or naive datetimes."""


def _require_aware(dt: datetime, label: str) -> None:
    if dt.tzinfo is None:
        raise ReplayError(f"{label} must be timezone-aware (UTC); got a naive datetime")


def candle_close_time(candle: dict, timeframe: str) -> datetime:
    """The moment this candle's window ends -- i.e. the earliest time its
    OHLC values could actually be known."""
    seconds = TIMEFRAME_SECONDS.get(timeframe)
    if seconds is None:
        raise ReplayError(f"unknown timeframe {timeframe!r}")
    open_time = candle["open_time"]
    _require_aware(open_time, "candle open_time")
    return open_time + timedelta(seconds=seconds)


def candles_closed_by(candles: list[dict], timeframe: str, as_of: datetime) -> list[dict]:
    """Only the candles fully closed at `as_of`, oldest-first.

    `candles` must be oldest-first. Returns a new list; never mutates the
    input, so the caller can hold one immutable full-history list and
    slice it repeatedly across the whole replay.
    """
    _require_aware(as_of, "as_of")
    seconds = TIMEFRAME_SECONDS.get(timeframe)
    if seconds is None:
        raise ReplayError(f"unknown timeframe {timeframe!r}")

    # Binary search, not a scan. `candles` is oldest-first and close time is
    # monotonic in open time, so the cut point is findable in O(log n).
    #
    # This is the backtester's hottest line by a wide margin: it runs once per
    # timeframe per decision point, and a 14-day sweep over 15,000 bars made it
    # roughly 400 million comparisons -- enough that a sweep had to be
    # interrupted rather than waited out. The result is identical; only the
    # cost changes.
    duration = timedelta(seconds=seconds)

    # Endpoint check, O(1). The scan this replaced happened to tolerate
    # newest-first input and return something plausible; bisect cannot, and
    # silently returning the wrong slice would be far worse than refusing.
    # Only the endpoints are compared -- verifying full sortedness every call
    # would cost exactly the O(n) the bisect exists to avoid.
    if len(candles) > 1:
        first, last = candles[0]["open_time"], candles[-1]["open_time"]
        if first.tzinfo is None or last.tzinfo is None:
            raise ReplayError("candle open_time must be timezone-aware (UTC)")
        if first > last:
            raise ReplayError(
                "candles must be oldest-first; this list is newest-first"
            )

    lo, hi = 0, len(candles)
    while lo < hi:
        mid = (lo + hi) // 2
        open_time = candles[mid]["open_time"]
        if open_time.tzinfo is None:
            raise ReplayError("candle open_time must be timezone-aware (UTC)")
        if open_time + duration <= as_of:
            lo = mid + 1
        else:
            hi = mid
    return candles[:lo]


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
