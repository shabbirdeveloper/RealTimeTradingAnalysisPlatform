"""
The strategy contract (spec Phase 18) and the scoring budget (Phase 21).

WHY THREE NAMED STRATEGIES INSTEAD OF ONE SCORE
-----------------------------------------------
The old engine produced a single blended number. When it won 46% of the
time, that number could not say which idea was losing -- trend
continuation and level rejection had been averaged into one figure long
before anything was measured. Three strategies, each emitting its own
CALL and PUT with its own reasons, make per-strategy accuracy a column in
a report (Phase 36) rather than an unanswerable question.

THE BUDGET
----------
Every strategy scores each side out of the same 100 points, so their
outputs are comparable and a threshold means one thing:

    Trend               0-20
    Structure           0-20
    Momentum            0-20
    Price action        0-15
    Support/resistance  0-10
    Volatility          0-10
    Entry timing        0-5

A strategy awards only the categories it actually has evidence for. An
unread category scores zero rather than half -- so a market a strategy
cannot see produces a LOW score, not a middling one. This is the same
principle as the None-not-50 rule in the feature engine, and it is what
lets a minimum-score threshold reject ignorance as well as disagreement.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from app.otc.features import MarketContext

MAX_TREND = 20
MAX_STRUCTURE = 20
MAX_MOMENTUM = 20
MAX_PRICE_ACTION = 15
MAX_LEVELS = 10
MAX_VOLATILITY = 10
MAX_ENTRY_TIMING = 5

MAX_TOTAL = (
    MAX_TREND + MAX_STRUCTURE + MAX_MOMENTUM + MAX_PRICE_ACTION
    + MAX_LEVELS + MAX_VOLATILITY + MAX_ENTRY_TIMING
)
assert MAX_TOTAL == 100


@dataclass
class SideScore:
    """One side's evidence, kept per category rather than as a total, so a
    stored signal can later be asked *why* it scored what it did."""

    trend: int = 0
    structure: int = 0
    momentum: int = 0
    price_action: int = 0
    levels: int = 0
    volatility: int = 0
    entry_timing: int = 0
    reasons: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return min(
            MAX_TOTAL,
            self.trend + self.structure + self.momentum + self.price_action
            + self.levels + self.volatility + self.entry_timing,
        )

    def award(self, category: str, points: int, reason: str) -> None:
        """Add points and record why. Points are clamped to the category's
        budget so a strategy cannot quietly outweigh the others by awarding
        30 points of 'momentum'."""
        cap = _CAPS[category]
        current = getattr(self, category)
        granted = max(0, min(points, cap - current))
        if granted <= 0:
            return
        setattr(self, category, current + granted)
        self.reasons.append(reason)


_CAPS = {
    "trend": MAX_TREND,
    "structure": MAX_STRUCTURE,
    "momentum": MAX_MOMENTUM,
    "price_action": MAX_PRICE_ACTION,
    "levels": MAX_LEVELS,
    "volatility": MAX_VOLATILITY,
    "entry_timing": MAX_ENTRY_TIMING,
}


@dataclass(frozen=True)
class StrategyVerdict:
    """What one strategy concluded. `call` and `put` are independent: both
    are low when the strategy has little evidence, and they need not sum to
    100. That gap is information -- it says nobody is committing -- and
    collapsing it into `put = 100 - call` would manufacture conviction out
    of silence."""

    name: str
    call: SideScore
    put: SideScore
    warnings: list[str] = field(default_factory=list)

    @property
    def call_total(self) -> int:
        return self.call.total

    @property
    def put_total(self) -> int:
        return self.put.total

    @property
    def difference(self) -> int:
        return abs(self.call_total - self.put_total)

    @property
    def leader(self) -> str | None:
        if self.call_total == self.put_total:
            return None
        return "CALL" if self.call_total > self.put_total else "PUT"


class Strategy(Protocol):
    name: str

    def evaluate(self, context: MarketContext) -> StrategyVerdict:
        ...
