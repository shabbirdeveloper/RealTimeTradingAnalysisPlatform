"""
Economic calendar provider abstraction (spec section 8).

Deliberately mirrors `app/market_data/base.py`: one narrow interface, so
swapping or adding a calendar feed is a single small class and nothing
else in the system changes.

No concrete paid/keyed provider is implemented yet -- picking one is a
cost and signup decision, and the surveyed options are either paid
(Trading Economics, FinanceFlow) or third-party scrapers of sites whose
terms don't clearly permit it. Rather than hard-wire a fragile or
questionable source, the system runs with `NullCalendarProvider` and is
explicit everywhere that no calendar data exists -- the signal engine
keeps warning that news is unscreened, and the calendar page says so.

To add a real feed: implement `fetch_upcoming()`, return
`EconomicEvent`s with tz-aware UTC times, and select it in
`app/news/factory.py`. Nothing else needs to change.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime


class CalendarError(Exception):
    """Any failure fetching calendar data."""


class ProviderEvent:
    """One event as returned by a provider, before storage.

    Plain class rather than the pydantic model used elsewhere so this
    module stays dependency-free and unit-testable without installs.
    """

    __slots__ = ("event_name", "currency", "event_time", "impact", "previous", "forecast", "actual")

    def __init__(
        self,
        event_name: str,
        currency: str,
        event_time: datetime,
        impact: str,
        previous: str | None = None,
        forecast: str | None = None,
        actual: str | None = None,
    ) -> None:
        if event_time.tzinfo is None:
            raise ValueError("event_time must be timezone-aware (UTC)")
        if impact.upper() not in ("HIGH", "MEDIUM", "LOW"):
            raise ValueError(f"unknown impact {impact!r}")
        self.event_name = event_name
        self.currency = currency.upper()
        self.event_time = event_time
        self.impact = impact.upper()
        self.previous = previous
        self.forecast = forecast
        self.actual = actual


class EconomicCalendarProvider(ABC):
    name: str = "unknown"

    @property
    def is_configured(self) -> bool:
        """False means this provider cannot supply data (no key, no feed).
        Callers must treat that as 'no calendar data exists' and stay
        honest about it -- never as 'no events, therefore all clear'."""
        return True

    @abstractmethod
    async def fetch_upcoming(self, days_ahead: int = 7) -> list[ProviderEvent]:
        """Events from now through `days_ahead`. Raises CalendarError on
        failure -- callers must not treat a failure as an empty calendar."""


class NullCalendarProvider(EconomicCalendarProvider):
    """The honest default: no calendar feed is configured.

    Returns no events AND reports `is_configured = False`, so callers can
    tell "the calendar says nothing is scheduled" apart from "there is no
    calendar". Conflating those two would silently turn an unprotected
    system into one that looks protected, which is exactly the class of
    fake-safety this project must avoid.
    """

    name = "none"

    @property
    def is_configured(self) -> bool:
        return False

    async def fetch_upcoming(self, days_ahead: int = 7) -> list[ProviderEvent]:
        return []
