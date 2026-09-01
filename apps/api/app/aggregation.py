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
    # Sub-minute timeframes exist for broker-OTC instruments, which are
    # traded on 15s-1m horizons. Public-market vendors do not sell sub-minute
    # data (Twelve Data's floor is 1min), so these are only ever populated
    # from a tick-level or OTC feed.
    S15 = "S15"
    S30 = "S30"
    M1 = "M1"
    M3 = "M3"
    M5 = "M5"
    M15 = "M15"
    H1 = "H1"
    H4 = "H4"


# Seconds, not minutes -- 15 seconds is not an integer number of minutes.
TIMEFRAME_SECONDS: dict[Timeframe, int] = {
    Timeframe.S15: 15,
    Timeframe.S30: 30,
    Timeframe.M1: 60,
    Timeframe.M3: 180,
    Timeframe.M5: 300,
    Timeframe.M15: 900,
    Timeframe.H1: 3600,
    Timeframe.H4: 14400,
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

    Anchored to midnight UTC and computed in seconds, which handles every
    supported timeframe with one expression: S15 buckets land on :00/:15/
    :30/:45 of each minute, M5/M15 on the usual minute boundaries, H4 on
    00:00/04:00/.../20:00.

    Anchoring to midnight rather than to the top of the hour matters as
    soon as a timeframe does not divide the hour evenly. Every timeframe
    supported today does, so this is identical to the previous hour-anchored
    logic -- but it stays correct for one that doesn't, instead of silently
    producing overlapping buckets.
    """
    dt = dt.astimezone(timezone.utc)
    seconds = TIMEFRAME_SECONDS[timeframe]
    day_start = dt.replace(hour=0, minute=0, second=0, microsecond=0)
    elapsed = int((dt - day_start).total_seconds())
    return day_start + timedelta(seconds=(elapsed // seconds) * seconds)


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

    source_seconds = TIMEFRAME_SECONDS[source_timeframe]
    target_seconds = TIMEFRAME_SECONDS[target_timeframe]
    if target_seconds <= source_seconds or target_seconds % source_seconds != 0:
        raise AggregationError(
            f"cannot aggregate {source_timeframe} into {target_timeframe}: "
            f"{target_seconds}s is not an exact multiple of {source_seconds}s"
        )
    expected_count = target_seconds // source_seconds

    buckets: dict[datetime, list[Candle]] = {}
    for candle in source_candles:
        bucket_key = _bucket_start(candle.open_time, target_timeframe)
        buckets.setdefault(bucket_key, []).append(candle)

    results: list[Candle] = []
    for bucket_start, bars in buckets.items():
        bars_sorted = sorted(bars, key=lambda c: c.open_time)
        bucket_end = bucket_start + timedelta(seconds=target_seconds)

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
