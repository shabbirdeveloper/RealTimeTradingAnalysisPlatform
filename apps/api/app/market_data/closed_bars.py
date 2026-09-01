"""
Rejects the still-forming bar at the ingestion boundary (audit FIN-04).

THE PROBLEM
-----------
Time-series market APIs conventionally include the IN-PROGRESS bar as the
newest value: at 10:07 a 5-minute feed returns a bar stamped 10:05 whose
high/low/close so far are two minutes of a five-minute window. Stored as
if it were a finished candle, it corrupts every indicator computed from
it -- and, worse, it is not reproducible. The next poll overwrites the
same bar with different numbers.

The subtler damage is to measurement. The backtester replays stored
history and, by then, that bar has its FINAL close. So the backtest sees
a bar the live engine only saw half of: it is systematically
better-informed than live was. Every backtested win rate is then
optimistic by an amount nobody can quantify, which is precisely the kind
of silent bias this project exists to avoid.

WHY THIS FILTER RUNS REGARDLESS OF WHAT THE PROVIDER DOES
---------------------------------------------------------
Twelve Data's docs do not state whether the newest value is closed, and
the question could not be answered from here. That turns out not to
matter: the filter is a no-op if the provider only ever returns closed
bars, and a fix if it doesn't. Making the answer irrelevant is a better
outcome than discovering it.

`split_closed` still reports what it dropped, so production answers the
question empirically within one poll -- see the collector's health
report.

ONE DEFINITION OF "CLOSED", SHARED WITH THE BACKTESTER
------------------------------------------------------
The rule and the interval table are imported from app.backtesting.replay
rather than restated here. Two definitions of "closed" that drift apart
IS the bug described above. The dependency direction is unusual on
purpose; the alternative is a duplicated constant in the one place where
duplication causes exactly the harm being prevented.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol, Sequence, TypeVar

from app.backtesting.replay import TIMEFRAME_SECONDS, ReplayError


class HasOpenTime(Protocol):
    open_time: datetime


T = TypeVar("T", bound=HasOpenTime)


@dataclass(frozen=True)
class ClosedBarSplit:
    """What survived ingestion, and what didn't."""

    closed: list
    # Bars whose window had not ended yet. A steady count of 1 per poll is
    # the expected shape when a provider includes the forming bar.
    forming: list
    # Bars opening in the FUTURE. Not a partial bar -- a bar that cannot
    # exist. Means the provider's clock, our clock, or the timezone
    # handling is wrong, and none of the data can be trusted until it is
    # explained. Separated from `forming` so a real fault is never filed
    # under a routine one.
    future: list

    @property
    def dropped(self) -> int:
        return len(self.forming) + len(self.future)


def interval_seconds(timeframe: str) -> int:
    seconds = TIMEFRAME_SECONDS.get(timeframe)
    if seconds is None:
        raise ReplayError(f"unknown timeframe {timeframe!r}")
    return seconds


def split_closed(
    candles: Sequence[T], timeframe: str, now: datetime
) -> ClosedBarSplit:
    """Partition `candles` into closed / still-forming / impossible.

    A bar is closed when `open_time + interval <= now` -- identical to the
    backtester's rule, deliberately.

    NO GRACE MARGIN, on purpose. A tolerance to absorb clock skew would
    re-admit partial bars, which is the whole problem. The costs are
    wildly asymmetric: dropping a genuinely-closed bar loses nothing (the
    next poll re-fetches it and the upsert is idempotent), while admitting
    a partial one corrupts indicators and quietly biases every backtest
    measured against them. When in doubt, wait.
    """
    if now.tzinfo is None:
        raise ReplayError("now must be timezone-aware (UTC); got a naive datetime")

    duration = timedelta(seconds=interval_seconds(timeframe))
    closed: list = []
    forming: list = []
    future: list = []

    for candle in candles:
        open_time = candle.open_time
        if open_time.tzinfo is None:
            raise ReplayError("candle open_time must be timezone-aware (UTC)")
        if open_time > now:
            future.append(candle)
        elif open_time + duration <= now:
            closed.append(candle)
        else:
            forming.append(candle)

    return ClosedBarSplit(closed=closed, forming=forming, future=future)
