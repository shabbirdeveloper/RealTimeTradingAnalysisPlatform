"""
Regime to strategy routing (spec Phase 19).

Running every strategy in every regime is what makes an ensemble look
smart and behave badly: a mean-reversion idea will always find something
to say during a trend, and averaging it with a trend idea produces a
number that describes neither market. Each strategy runs only where its
premise holds.

CHOPPY and UNKNOWN route to nothing at all. That is not a gap in the
table -- it is the table's most important entry.
"""

from __future__ import annotations

from app.otc.config import CONFIG
from app.otc.regime import (
    BREAKOUT,
    CHOPPY,
    HIGH_VOLATILITY,
    LOW_VOLATILITY,
    PULLBACK,
    RANGING,
    TRENDING_DOWN,
    TRENDING_UP,
    UNKNOWN,
)
from app.otc.strategies.base import Strategy
from app.otc.strategies.level_rejection import LevelRejection
from app.otc.strategies.momentum_continuation import MomentumContinuation
from app.otc.strategies.trend_pullback import TrendPullback

_REGISTRY: dict[str, Strategy] = {
    "trend_pullback": TrendPullback(),
    "momentum_continuation": MomentumContinuation(),
    "level_rejection": LevelRejection(),
}

ROUTING: dict[str, tuple[str, ...]] = {
    TRENDING_UP: ("trend_pullback", "momentum_continuation"),
    TRENDING_DOWN: ("trend_pullback", "momentum_continuation"),
    PULLBACK: ("trend_pullback",),
    BREAKOUT: ("momentum_continuation",),
    RANGING: ("level_rejection",),
    # An unusually wide range is where rejection setups are cleanest and
    # momentum entries are most likely to be buying the last candle.
    HIGH_VOLATILITY: ("level_rejection",),
    # A quiet tape is where rejection setups are cleanest -- price is
    # respecting levels rather than running through them. Routing it to
    # nothing was my addition, not the spec's, and it silenced the engine
    # completely on an instrument whose ATR percentile sits low for long
    # stretches. The volatility PENALTY inside each strategy is the right
    # place to express "this is thin", not a blanket regime veto.
    LOW_VOLATILITY: ("level_rejection",),
    CHOPPY: (),
    UNKNOWN: (),
}


def strategies_for(regime: str) -> list[Strategy]:
    """The strategies permitted in this regime, minus any disabled in
    config. An unknown regime routes to nothing rather than to everything
    -- failing closed, because the alternative is trading a market the
    classifier could not read."""
    names = ROUTING.get(regime, ())
    return [
        _REGISTRY[name]
        for name in names
        if CONFIG.strategies.get(name, False) and name in _REGISTRY
    ]
