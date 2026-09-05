"""
The decision object (spec Phase 27) and the vocabulary around it.

Kept separate from the engine that produces it so that storage, the API,
the backtester and the notifier can all depend on the shape without
depending on the logic -- and so a rejected setup and an accepted one are
literally the same record with a different status. Phase 32 wants rejected
candidates stored and analysable; that is only cheap if rejection is a
field rather than a different code path that throws the evidence away.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum


class Direction(str, Enum):
    CALL = "CALL"
    PUT = "PUT"
    NO_TRADE = "NO_TRADE"


class SignalStatus(str, Enum):
    # Produced but not published: below threshold, filtered, or vetoed.
    REJECTED = "REJECTED"
    # Published and awaiting expiry.
    ACTIVE = "ACTIVE"
    WON = "WON"
    LOST = "LOST"
    DRAW = "DRAW"
    # The feed went unhealthy between entry and expiry, so the outcome
    # cannot be attributed to the decision. Deliberately not a loss:
    # counting infrastructure failures as losses corrupts the win rate in
    # the pessimistic direction, which is no more honest than the reverse.
    INVALIDATED = "INVALIDATED"


@dataclass(frozen=True)
class CategoryScores:
    trend: int = 0
    structure: int = 0
    momentum: int = 0
    price_action: int = 0
    levels: int = 0
    volatility: int = 0
    entry_timing: int = 0


@dataclass(frozen=True)
class OTCDecision:
    """One evaluation's complete result -- signal or not.

    `direction` is NO_TRADE for anything that did not clear every gate,
    and `rejection_reasons` then says which gate. Both are always
    populated: a NO_TRADE with no reason is indistinguishable from a bug.
    """

    symbol: str
    broker: str
    generated_at: datetime
    direction: Direction
    status: SignalStatus

    price: float
    expiry_seconds: int

    regime: str
    regime_reason: str

    strategy: str | None
    call_score: int
    put_score: int

    call_categories: CategoryScores
    put_categories: CategoryScores

    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    rejection_reasons: list[str] = field(default_factory=list)

    feed_status: str = "HEALTHY"
    fingerprint: str | None = None

    @property
    def is_signal(self) -> bool:
        return self.direction is not Direction.NO_TRADE

    @property
    def score(self) -> int:
        """The winning side's score. Meaningless when there is no winner,
        so callers should gate on `is_signal` first."""
        return max(self.call_score, self.put_score)

    @property
    def difference(self) -> int:
        return abs(self.call_score - self.put_score)

    @property
    def expiry_at(self) -> datetime:
        return self.generated_at + timedelta(seconds=self.expiry_seconds)

    @property
    def entry_price(self) -> float | None:
        return self.price if self.is_signal else None
