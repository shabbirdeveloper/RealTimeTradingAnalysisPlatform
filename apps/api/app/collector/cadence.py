"""
Per-asset polling cadence.

One global interval forces a bad trade-off. Fast enough to see an M5 bar
promptly during London/New York means burning the same rate on a dead
Asian session and on two crypto pairs that nobody is trading off M5 --
and Twelve Data's free tier is 800 requests/day, so overspending doesn't
degrade gracefully. It stops. A collector that exhausts its quota at
10am has no data for the rest of the day, which is strictly worse than
polling slower all day.

So cadence is per asset and per hour:

  Forex/gold, London or New York open   every 5 minutes
  Forex/gold, otherwise                 every 15 minutes
  Continuous instruments (crypto/OTC)   every 30 minutes

Worth being explicit about what this does NOT do: polling faster does not
produce more signals. An M5 bar closes every five minutes no matter how
often it is fetched; a shorter interval means seeing a closed bar sooner,
so an entry price is fresher. Whether a setup clears the quality bar is
decided by the engine, not by the collector's clock.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

# Twelve Data's free tier. Kept here so the budget test has something to
# assert against, and so exceeding it is a failing test rather than a
# surprise at 10am.
FREE_TIER_REQUESTS_PER_DAY = 800

# London opens 07:00 UTC, New York closes 21:00 UTC (see
# features/structure.session_for_time, which this must agree with).
ACTIVE_START_HOUR = 7
ACTIVE_END_HOUR = 21


@dataclass(frozen=True)
class Cadence:
    active_seconds: int
    quiet_seconds: int

    def seconds_at(self, now: datetime) -> int:
        return self.active_seconds if is_active_hours(now) else self.quiet_seconds


# Sized against FREE_TIER_REQUESTS_PER_DAY for the instruments actually
# enabled, and the arithmetic is the point:
#
#   1 asset x (14h / 2min  +  10h / 5min)  =  420 + 120  =  540 of 800
#
# One pair buys a two-minute cadence during London and New York, which is
# where a 300-second expiry is actually traded. The M1 entry bar changes
# every minute, so two minutes sees every other one close -- as close to
# live as this tier allows.
#
# This is why concentrating on one instrument is not merely a focus
# decision: five assets on this cadence would cost 2700 requests a day
# against a tier of 800, and the quota would be gone before lunch.
FX_CADENCE = Cadence(active_seconds=120, quiet_seconds=300)
CONTINUOUS_CADENCE = Cadence(active_seconds=900, quiet_seconds=900)

# The scheduler's own tick. Must divide every cadence above, or an asset
# whose interval is not a multiple of the tick drifts later each cycle --
# a 120-second asset checked on a 300-second tick is really a 300-second
# asset, and the faster cadence would exist only in the config.
TICK_SECONDS = 60


def is_active_hours(now: datetime) -> bool:
    hour = now.astimezone(timezone.utc).hour
    return ACTIVE_START_HOUR <= hour < ACTIVE_END_HOUR


def cadence_for(symbol: str) -> Cadence:
    from app.instruments import trades_continuously

    return CONTINUOUS_CADENCE if trades_continuously(symbol) else FX_CADENCE


def interval_seconds(symbol: str, now: datetime) -> int:
    return cadence_for(symbol).seconds_at(now)


def should_poll(symbol: str, now: datetime, last_polled: datetime | None) -> bool:
    """True when this asset is due. `last_polled=None` (first cycle after a
    restart) always polls -- a restart should not silently skip an asset."""
    if last_polled is None:
        return True
    due = last_polled + timedelta(seconds=interval_seconds(symbol, now))
    # A tolerance, because the scheduler fires a hair early or late and an
    # asset that misses its slot by two seconds would wait a whole extra
    # tick -- halving its real cadence.
    return now >= due - timedelta(seconds=5)


def daily_request_estimate(symbols: list[str]) -> float:
    """Requests per 24h if every asset polls on schedule all day.

    Deliberately pessimistic for forex: it assumes a full 24h day, ignoring
    the weekend and Friday-evening closures that make the real number
    lower. Better to over-estimate a budget than to discover the ceiling by
    hitting it.
    """
    active_hours = ACTIVE_END_HOUR - ACTIVE_START_HOUR
    quiet_hours = 24 - active_hours
    total = 0.0
    for symbol in symbols:
        cadence = cadence_for(symbol)
        total += active_hours * 3600 / cadence.active_seconds
        total += quiet_hours * 3600 / cadence.quiet_seconds
    return total
