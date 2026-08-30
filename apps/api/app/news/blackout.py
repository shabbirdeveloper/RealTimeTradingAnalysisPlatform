"""
News protection (spec section 8).

Decides, for one asset at one moment, whether trading should be paused
because a relevant high-impact economic event is near:

    ... quiet ...
    [ pre-news window ]   -> SIGNALS PAUSED
    [ event moment    ]   -> NEWS MODE
    [ post-event window ] -> SIGNALS PAUSED (stabilization)
    ... quiet ...

Pure functions over a list of events -- no I/O, no clock of its own, no
provider coupling. That keeps this fully unit-testable and means the
policy is identical no matter which calendar feed the events came from.

Blackout durations are configurable (spec section 8 requires this
explicitly): the defaults below are conventional starting values, NOT
validated ones. Once the backtester has enough real history it can
measure whether these windows actually help, which is the only honest way
to set them.

Relevance: an event only matters for an asset whose price is exposed to
that currency. USD events move all three configured instruments; EUR
events only EURUSD; GBP events only GBPUSD. Gold is quoted in USD, so
XAUUSD is USD-sensitive -- which is why a US CPI print is a
gold-relevant event even though "XAU" contains no currency code.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

# Which currencies' news can move each configured instrument.
ASSET_CURRENCIES: dict[str, frozenset[str]] = {
    "XAUUSD": frozenset({"USD"}),
    "EURUSD": frozenset({"EUR", "USD"}),
    "GBPUSD": frozenset({"GBP", "USD"}),
}

# Impact levels that trigger a blackout at all. MEDIUM/LOW events are
# stored and displayed on the calendar, but do not pause trading --
# pausing on every low-impact print would suppress most of the session
# for no established benefit.
BLACKOUT_IMPACTS: frozenset[str] = frozenset({"HIGH"})


@dataclass(frozen=True)
class BlackoutConfig:
    """Spec section 8: "Make blackout durations configurable."

    These defaults are conventional, not validated. Treat them as a
    starting point to be tested against real history, not as tuned
    parameters.
    """
    minutes_before: int = 30
    minutes_after: int = 30

    def __post_init__(self) -> None:
        if self.minutes_before < 0 or self.minutes_after < 0:
            raise ValueError("blackout windows cannot be negative")


@dataclass(frozen=True)
class EconomicEvent:
    event_name: str
    currency: str
    event_time: datetime  # must be timezone-aware UTC
    impact: str           # HIGH | MEDIUM | LOW


@dataclass(frozen=True)
class BlackoutStatus:
    """`active` True means signal generation should be suppressed.

    `reason` is written for the trader, not the log: it names the event
    and how far away it is, so a NO_TRADE explains itself.
    """
    active: bool
    phase: str  # "CLEAR" | "PRE_NEWS" | "POST_NEWS"
    reason: str | None = None
    event_name: str | None = None
    event_time: datetime | None = None


def is_relevant(event: EconomicEvent, asset: str) -> bool:
    return event.currency.upper() in ASSET_CURRENCIES.get(asset, frozenset())


def relevant_events(events: list[EconomicEvent], asset: str) -> list[EconomicEvent]:
    return [e for e in events if is_relevant(e, asset)]


def evaluate_blackout(
    events: list[EconomicEvent],
    asset: str,
    now: datetime,
    config: BlackoutConfig | None = None,
) -> BlackoutStatus:
    """Whether `asset` is inside a high-impact news blackout at `now`.

    When several events overlap, the one whose event_time is nearest to
    `now` is reported -- that is the one a trader would actually be
    watching.
    """
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware (UTC)")
    config = config or BlackoutConfig()

    before = timedelta(minutes=config.minutes_before)
    after = timedelta(minutes=config.minutes_after)

    candidates: list[tuple[timedelta, EconomicEvent, str]] = []
    for event in events:
        if event.impact.upper() not in BLACKOUT_IMPACTS:
            continue
        if not is_relevant(event, asset):
            continue
        if event.event_time.tzinfo is None:
            raise ValueError(f"event {event.event_name!r} has a naive event_time")

        if event.event_time - before <= now < event.event_time:
            candidates.append((event.event_time - now, event, "PRE_NEWS"))
        elif event.event_time <= now <= event.event_time + after:
            candidates.append((now - event.event_time, event, "POST_NEWS"))

    if not candidates:
        return BlackoutStatus(active=False, phase="CLEAR")

    distance, event, phase = min(candidates, key=lambda c: c[0])
    minutes = int(distance.total_seconds() // 60)

    if phase == "PRE_NEWS":
        reason = (
            f"High-impact {event.currency} news in {minutes} min "
            f"({event.event_name}) — signals paused before the release."
        )
    else:
        reason = (
            f"High-impact {event.currency} news {minutes} min ago "
            f"({event.event_name}) — waiting for the market to stabilize."
        )

    return BlackoutStatus(
        active=True,
        phase=phase,
        reason=reason,
        event_name=event.event_name,
        event_time=event.event_time,
    )
