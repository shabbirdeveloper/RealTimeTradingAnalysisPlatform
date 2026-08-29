"""
Candle timeframe aggregation.

Pure, dependency-free by design: this module has zero third-party imports
so it can be unit tested in complete isolation from the market-data
provider, the database, and the network. The collector calls this after
fetching M5 candles from the provider -- everything above M5 (M15/H1/H4)
is DERIVED here rather than fetched separately, which both keeps API
credit usage down (spec section: quality over quantity applies to API
calls too) and gives one single, testable place where OHLC aggregation
bugs would live, instead of trusting four separate provider responses to
agree with each other.

Correctness rule (this is the part most likely to introduce a silent bug,
so it gets extra care): NEVER emit a bucket that might still be forming.
A bucket is only emitted once every source candle it should contain has
actually closed. See aggregate_candles()'s docstring for the two ways a
bucket qualifies as closed.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from enum import Enum


class Timeframe(str, Enum):
    M5 = "M5"
    M15 = "M15"
    H1 = "H1"
    H4 = "H4"


TIMEFRAME_MINUTES: dict[Timeframe, int] = {
    Timeframe.M5: 5,
    Timeframe.M15: 15,
    Timeframe.H1: 60,
    Timeframe.H4: 240,
}


class AggregationError(ValueError):
    """Raised on programmer error (bad timeframe pairing, naive datetime),
    never on ordinary data gaps -- those are handled, not raised."""


@dataclass(frozen=True)
class Candle:
    open_time: datetime  # must be tz-aware, UTC
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal | None = None

    def __post_init__(self) -> None:
        if self.open_time.tzinfo is None:
            raise AggregationError("Candle.open_time must be timezone-aware (UTC)")


def _bucket_start(dt: datetime, timeframe: Timeframe) -> datetime:
    """Floor a UTC timestamp to the start of its timeframe bucket.

    M5/M15 buckets align to the top of the hour. H1 buckets align to the
    top of the hour. H4 buckets align to 00:00/04:00/08:00/12:00/16:00/
    20:00 UTC -- i.e. hour-of-day integer-divided by 4.
    """
    dt = dt.astimezone(timezone.utc)
    minutes = TIMEFRAME_MINUTES[timeframe]
    if minutes < 60:
        floored_minute = (dt.minute // minutes) * minutes
        return dt.replace(minute=floored_minute, second=0, microsecond=0)
    hours = minutes // 60
    floored_hour = (dt.hour // hours) * hours
    return dt.replace(hour=floored_hour, minute=0, second=0, microsecond=0)


def aggregate_candles(
    source_candles: list[Candle],
    source_timeframe: Timeframe,
    target_timeframe: Timeframe,
    *,
    now: datetime | None = None,
) -> list[Candle]:
    """Aggregate source-timeframe candles (e.g. M5) into target-timeframe
    candles (e.g. H1), returning ONLY buckets that are fully closed.

    A bucket qualifies as closed when either:
      1. it contains the exact expected number of source bars (e.g. 12 M5
         bars make one closed H1 bar) -- the strict, gap-free case; or
      2. `now` is supplied and now >= bucket_end -- the wall clock says
         the bar has genuinely closed even if the provider is missing a
         bar or two. Missing bars are the provider's problem to surface
         (as a MarketDataError upstream), never papered over by
         fabricating a bar here -- this function only ever aggregates
         bars it was actually handed.

    Omitting `now` is the strict/conservative mode: a bucket is only ever
    emitted if every expected bar is present. This is what the collector
    should use when it wants zero risk of treating an in-progress bar as
    closed.
    """
    if source_timeframe == target_timeframe:
        raise AggregationError("source and target timeframe must differ")

    source_minutes = TIMEFRAME_MINUTES[source_timeframe]
    target_minutes = TIMEFRAME_MINUTES[target_timeframe]
    if target_minutes <= source_minutes or target_minutes % source_minutes != 0:
        raise AggregationError(
            f"cannot aggregate {source_timeframe} into {target_timeframe}: "
            f"{target_minutes} is not an exact multiple of {source_minutes}"
        )
    expected_count = target_minutes // source_minutes

    buckets: dict[datetime, list[Candle]] = {}
    for candle in source_candles:
        bucket_key = _bucket_start(candle.open_time, target_timeframe)
        buckets.setdefault(bucket_key, []).append(candle)

    results: list[Candle] = []
    for bucket_start, bars in buckets.items():
        bars_sorted = sorted(bars, key=lambda c: c.open_time)
        bucket_end = bucket_start + timedelta(minutes=target_minutes)

        is_complete_set = len(bars_sorted) == expected_count
        is_time_elapsed = now is not None and now >= bucket_end

        if not is_complete_set and not is_time_elapsed:
            continue  # still forming, or has gaps we won't paper over yet

        volumes = [c.volume for c in bars_sorted if c.volume is not None]
        results.append(
            Candle(
                open_time=bucket_start,
                open=bars_sorted[0].open,
                high=max(c.high for c in bars_sorted),
                low=min(c.low for c in bars_sorted),
                close=bars_sorted[-1].close,
                volume=sum(volumes, Decimal(0)) if volumes else None,
            )
        )

    results.sort(key=lambda c: c.open_time)
    return results
