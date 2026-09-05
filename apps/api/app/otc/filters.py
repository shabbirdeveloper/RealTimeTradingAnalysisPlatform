"""
The no-trade engine (spec Phase 24), penalties (22) and entry timing (25).

NO TRADE is the default here, not the fallback. Every function returns the
reasons a setup should be refused, and the engine publishes only when that
list is empty. Written this way round deliberately: a filter chain that
returns True/False loses the reason by the time anyone asks, and "why did
it not signal?" is the question this project asks most.
"""

from __future__ import annotations

from app.otc.config import CONFIG
from app.otc.features import MarketContext
from app.otc.regime import NO_TRADE_REGIMES
from app.otc.strategies.base import StrategyVerdict

# A candle this many ATRs beyond the recent norm has already made the move
# a 5-minute expiry was meant to capture (Phase 25).
_SPIKE_ATR = 1.8


def warmup_failures(context: MarketContext) -> list[str]:
    """Timeframes whose indicators have not converged. An EMA50 computed
    from 20 bars is arithmetic, not evidence."""
    problems: list[str] = []
    for timeframe in ("M15", "M5", "M3", "M1"):
        frame = context.frame(timeframe)
        if frame is None:
            problems.append(f"{timeframe} candles missing")
        elif len(frame.candles) < CONFIG.min_bars_per_timeframe:
            problems.append(
                f"{timeframe} has {len(frame.candles)} bars, needs {CONFIG.min_bars_per_timeframe}"
            )
        elif not frame.ready:
            problems.append(f"{timeframe} indicators have not converged")
    return problems


def regime_failures(context: MarketContext) -> list[str]:
    if context.regime in NO_TRADE_REGIMES:
        return [f"regime is {context.regime}"]
    return []


def scoring_failures(verdict: StrategyVerdict) -> list[str]:
    """Phase 23's two gates, kept separate because they reject different
    markets and the distinction matters when reading rejected setups.

    A low score means thin evidence. A small difference means CONFLICTING
    evidence -- CALL 79 against PUT 68 is not a 79-quality setup, it is a
    market with no clear direction that happens to lean. Merging the two
    into one 'quality' number is what made the old engine's threshold
    sweep move the win rate by 0.2 points across 1,575 trades.
    """
    problems: list[str] = []
    leader = verdict.leader
    best = max(verdict.call_total, verdict.put_total)

    if leader is None:
        return ["CALL and PUT scored identically"]
    if best < CONFIG.minimum_score:
        problems.append(f"score {best} below the {CONFIG.minimum_score} floor")
    if verdict.difference < CONFIG.minimum_directional_difference:
        problems.append(
            f"CALL {verdict.call_total} vs PUT {verdict.put_total} -- "
            f"separation {verdict.difference} below the {CONFIG.minimum_directional_difference} floor"
        )
    return problems


def entry_timing_failures(context: MarketContext, direction: str) -> list[str]:
    """Phase 25. A correct direction entered one candle too late loses just
    as completely as a wrong one, and on a 300-second expiry there is no
    time to recover from it.

    The specific refusal: entering a CALL immediately after a large bullish
    candle, or a PUT after a large bearish one. That candle is the move.
    """
    problems: list[str] = []
    entry = context.frame("S30") or context.frame("M1")
    structure = context.frame("M5")
    if entry is None or entry.shape is None or structure is None or not structure.atr:
        return ["entry timeframe unavailable"]

    spike = entry.shape.range_size / structure.atr if structure.atr else 0.0
    if spike >= _SPIKE_ATR:
        moved_up = entry.shape.bullish
        if (direction == "CALL" and moved_up) or (direction == "PUT" and not moved_up):
            problems.append(
                f"entering straight after a {spike:.1f} ATR candle in the same direction"
            )

    # Closing against the intended direction on the entry bar means the
    # last thing price did was disagree.
    location = entry.shape.close_location
    if direction == "CALL" and location < 0.3:
        problems.append(f"entry candle closed near its low ({location:.0%} of range)")
    if direction == "PUT" and location > 0.7:
        problems.append(f"entry candle closed near its high ({location:.0%} of range)")

    return problems
