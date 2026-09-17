"""
Is this instrument's floor reachable at all?

WHY THIS EXISTS
---------------
DERIV_V75 ran 599 evaluations without producing a single signal. Nothing
was broken and nothing said anything: every cycle logged an ordinary
"score 34 below the 78 floor", which is exactly what a healthy, selective
engine logs. The difference only appeared when 599 of those lines were
parsed at once -- the best score the instrument had EVER reached was 77,
against a floor of 78.

That is not selectivity. It is a wall, and it looked identical to
selectivity from every individual log line.

So the engine now keeps the one number that separates them: the best
score it has ever seen for each symbol. When enough decisions have gone
by and that number is still under the floor, it says so plainly, instead
of leaving the fact to be rediscovered by whoever thinks to aggregate the
log.

It does NOT lower anything. How often a floor is cleared says nothing
about whether those setups win; only the backtest can answer that. This
just makes the difference between "declining" and "cannot speak" visible
on the day it starts mattering.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# symbol -> (best score ever seen, decisions counted)
_SEEN: dict[str, tuple[int, int]] = {}

# Enough cycles that a quiet stretch is not mistaken for a wall. At the
# broker feed's one-a-minute cadence this is about three hours.
_MIN_DECISIONS = 180

# How often to repeat the warning once it starts. Every cycle would bury
# the log it is trying to make readable.
_REPEAT_EVERY = 120


def record(symbol: str, best_score: int, floor: int) -> None:
    """Note one decision's best side score, and warn if the floor has never
    been reached in a meaningful number of decisions."""
    previous_best, count = _SEEN.get(symbol, (0, 0))
    best = max(previous_best, best_score)
    count += 1
    _SEEN[symbol] = (best, count)

    if best >= floor or count < _MIN_DECISIONS:
        return
    if count % _REPEAT_EVERY != 0:
        return

    logger.warning(
        "[UNREACHABLE] %s: %d decisions, best score ever %d, floor %d. "
        "No setup on this instrument has ever cleared the floor, so it cannot "
        "produce a signal at this setting. Run otc_backtest.py --symbol %s "
        "--sweep and set its entry in SYMBOL_THRESHOLDS from the result -- "
        "not by hand.",
        symbol, count, best, floor, symbol,
    )


def snapshot() -> dict[str, tuple[int, int]]:
    """For diagnostics: {symbol: (best score ever, decisions seen)}."""
    return dict(_SEEN)
