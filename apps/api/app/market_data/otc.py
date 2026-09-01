"""
The contract an OTC price source must satisfy, and the honest placeholder
that stands in until one is connected.

WHY A CONTRACT RATHER THAN A CONNECTOR
--------------------------------------
Quotex OTC prices are generated inside Quotex. No vendor sells them,
because there is nothing to sell -- it is the broker's internal series.
The only code that reaches them logs into a user's account over an
undocumented websocket, which the project spec (section 43) forbids,
which handles broker credentials, and which risks the account.

So this module does not fetch anything. It defines precisely what a feed
must provide for the engine to trust it, so that whatever eventually
supplies those prices is used correctly and its output is provably
attributable. Everything downstream -- storage, features, regime,
strategy, expiry, resolution, analytics -- is already written against
this boundary and needs no changes when a real source appears.

WHAT A CONFORMING SOURCE MUST GUARANTEE
---------------------------------------
1. CLOSED BARS ONLY, or bars explicitly marked unclosed. The still-forming
   bar corrupts indicators and makes the backtester better-informed than
   live was. See closed_bars.py.
2. UTC, timezone-aware timestamps. A naive timestamp is how a timezone bug
   becomes silent.
3. STABLE HISTORY. A bar, once closed, must never change value. If the
   source replays or revises bars, say so -- it invalidates backtesting.
4. HONEST PROVENANCE. The FeedDescriptor must name the broker whose
   generator produced the series. This is the single check standing between
   a real OTC signal and a convincing fiction.
5. FAILURE, NOT SUBSTITUTION. On any problem, raise. Never fall back to a
   public-market quote for the "same" pair -- that is the exact failure
   this whole design exists to prevent.

THE LIMITATION, RECORDED RATHER THAN HIDDEN
-------------------------------------------
Even a perfectly conforming OTC source has a property no engineering can
remove: the firm generating the prices is the firm paying the winning
trades, and the generator can change at any time without notice. A
backtested edge on such a series therefore carries no guarantee of
persisting. That is not a reason to refuse to build this -- it is a reason
the shadow-mode and calibration machinery matters more here than it would
on a real market, and why `history_is_stable` below is part of the
contract.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime

from app.market_data.errors import MarketDataError
from app.instruments import FeedDescriptor, FeedKind


class OTCFeedNotConnected(MarketDataError):
    """Raised when OTC analysis is requested but no OTC source is configured.

    Deliberately an error rather than an empty result. An empty candle list
    would flow downstream and surface as "insufficient history", which reads
    like a system that is warming up rather than one that has no data source
    at all. The distinction is the same one `calendar_available` draws in the
    news filter, and `MODEL_NOT_READY` draws for ML: absent capability must
    never be presentable as a quiet, ordinary state.
    """


@dataclass(frozen=True)
class OTCBar:
    """One closed bar from a broker's OTC series.

    Deliberately not the shared `Candle` schema: an OTC bar carries
    provenance and a closure flag that a public-market candle does not need,
    and forcing them into one type is how the two get confused.
    """

    symbol: str          # registry symbol, e.g. "EURUSD_OTC"
    open_time: datetime  # tz-aware UTC
    timeframe: str       # "S15" | "S30" | "M1" | ...
    open: float
    high: float
    low: float
    close: float
    is_closed: bool
    source: str          # feed name, e.g. "quotex_otc"
    tick_count: int | None = None

    def __post_init__(self) -> None:
        if self.open_time.tzinfo is None:
            raise ValueError("OTCBar.open_time must be timezone-aware (UTC)")
        if self.high < self.low:
            raise ValueError(f"OTCBar high {self.high} is below low {self.low}")
        for field, value in (("open", self.open), ("close", self.close)):
            if not self.low <= value <= self.high:
                raise ValueError(
                    f"OTCBar {field} {value} lies outside the bar's own high/low "
                    f"range [{self.low}, {self.high}] — the bar is malformed and "
                    "must not be stored."
                )


class OTCFeed(ABC):
    """Implement this to supply broker-OTC prices."""

    name: str
    broker: str
    # False when the source revises or replays bars after they close. A
    # feed that admits this cannot support backtesting, and the engine
    # should refuse to draw historical conclusions from it rather than
    # quietly producing numbers that mean nothing.
    history_is_stable: bool = True

    @property
    def descriptor(self) -> FeedDescriptor:
        return FeedDescriptor(name=self.name, kind=FeedKind.BROKER_OTC, broker=self.broker)

    @abstractmethod
    async def fetch_bars(self, symbol: str, timeframe: str, count: int) -> list[OTCBar]:
        """Most recent `count` CLOSED bars, oldest first.

        Raise on any failure. Never return a partial or substituted result:
        the caller's correct response to missing OTC data is to generate no
        signal, and it can only choose that if it is told.
        """
        raise NotImplementedError


class NoOTCFeedConfigured(OTCFeed):
    """The active OTC feed until a real one is connected.

    It refuses, loudly and with an explanation, rather than returning
    nothing. Returning nothing would let the platform present "no signals
    yet" — indistinguishable from a working system in a quiet market — when
    the truth is that no OTC data source exists at all.
    """

    name = "not_connected"
    broker = "NONE"
    history_is_stable = False

    async def fetch_bars(self, symbol: str, timeframe: str, count: int) -> list[OTCBar]:
        raise OTCFeedNotConnected(
            f"No OTC price source is configured, so {symbol!r} cannot be analysed. "
            "OTC prices are generated by the broker and are not available from any "
            "market-data vendor. Until a conforming OTCFeed is connected, this "
            "platform has no data for this instrument — and it will not substitute "
            "the real-market pair of the same name, which is an unrelated series."
        )


_active_feed: OTCFeed = NoOTCFeedConfigured()


def get_otc_feed() -> OTCFeed:
    return _active_feed


def set_otc_feed(feed: OTCFeed) -> None:
    """Register the OTC source. Validated here rather than trusted, because
    a feed that misreports its own provenance defeats every downstream check
    that depends on it."""
    if not isinstance(feed, OTCFeed):
        raise TypeError(f"{feed!r} does not implement the OTCFeed contract")
    if not getattr(feed, "name", None):
        raise ValueError("an OTC feed must have a non-empty name")
    if not getattr(feed, "broker", None) or feed.broker == "NONE":
        raise ValueError(
            "an OTC feed must name the broker whose generator produced the series — "
            "that name is what the provenance check compares against"
        )
    global _active_feed
    _active_feed = feed


def reset_otc_feed() -> None:
    global _active_feed
    _active_feed = NoOTCFeedConfigured()
