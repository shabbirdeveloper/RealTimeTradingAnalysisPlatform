"""
CALL and PUT scored independently, then made to compete (spec section 21).

WHY THIS REPLACES A SINGLE SCORE
--------------------------------
The engine used to choose a direction from timeframe agreement and then
score that one direction. Two problems followed from it.

First, the score could not disagree with the gate. It was computed as
`weighted_strength * 0.7 + aligned * 6`, where each timeframe's strength
was `50 + net_votes * 14` -- the same votes that had just chosen the
direction. A number derived from the decision cannot also be evidence
about the decision, which is the mechanical reason sweeping the threshold
from 55 to 74 moved the win rate by 0.2 points across 1,575 trades.

Second, and worse: netting votes destroyed the distinction between
agreement and conflict. Three voters up against two down nets to +1, and
so does one up against none. The first market is arguing with itself; the
second simply has thin evidence. A single netted score cannot tell you
which one you are looking at, and those are exactly the setups worth
telling apart.

WHAT IS SCORED
--------------
Both sides, from the same evidence, without either being derived from the
other. For each timeframe, the bullish voters contribute to the CALL
score and the bearish voters to the PUT score, weighted by that
timeframe's relevance to the expiry being considered. A voter that stayed
silent contributes to neither -- so an indecisive market produces two LOW
scores rather than one high one, which is the honest reading.

The two are NOT complements: call + put < 100 whenever voters abstain.
That gap is information (nobody is committing), and collapsing it into
`put = 100 - call` would manufacture conviction out of silence.

SEPARATION
----------
`score_difference` is what makes this worth having. CALL 78 against PUT
70 is not a 78-quality setup -- it is a market with no clear direction
that happens to lean. Requiring a minimum gap rejects it; the old single
score could not see it at all.

The default minimum gap is 0, which reproduces the previous behaviour
exactly. It is a parameter so gate_sweep.py can measure the right value
instead of anyone guessing it -- the same discipline applied to every
other threshold here.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.features.timeframe_bias import TimeframeBias

# Voters per timeframe: EMA20/50, EMA200, RSI, MACD, swing structure.
# Named rather than hardcoded at the call site so a sixth voter changes
# one number, not the scale of every score ever recorded.
VOTERS_PER_TIMEFRAME = 5


@dataclass(frozen=True)
class SideScores:
    call: int
    put: int

    @property
    def difference(self) -> int:
        return abs(self.call - self.put)

    @property
    def leader(self) -> str:
        if self.call == self.put:
            return "NO_TRADE"
        return "CALL" if self.call > self.put else "PUT"

    @property
    def uncommitted(self) -> int:
        """How much of the scale nobody claimed. High means the evidence was
        absent, not balanced -- a different failure from a tie."""
        return max(0, 100 - self.call - self.put)


def side_scores(
    timeframes: list[TimeframeBias],
    weights: dict[str, float] | None = None,
) -> SideScores:
    """Independent 0-100 scores for CALL and PUT.

    `weights` maps timeframe name to relevance for the expiry under
    consideration; missing entries weigh 1.0. Timeframes without enough
    history are excluded entirely rather than counted as neutral -- a
    warm-up gap is missing evidence, not evidence of balance.
    """
    usable = [t for t in timeframes if not t.insufficient_data]
    if not usable:
        return SideScores(call=0, put=0)

    weights = weights or {}
    bull_total = 0.0
    bear_total = 0.0
    weight_total = 0.0

    for tf in usable:
        w = float(weights.get(tf.timeframe, 1.0))
        if w <= 0:
            continue
        bull_total += w * (tf.bull_votes / VOTERS_PER_TIMEFRAME)
        bear_total += w * (tf.bear_votes / VOTERS_PER_TIMEFRAME)
        weight_total += w

    if weight_total == 0:
        return SideScores(call=0, put=0)

    return SideScores(
        call=int(round(100 * bull_total / weight_total)),
        put=int(round(100 * bear_total / weight_total)),
    )
