"""
Historical backtest replay (spec section 13).

Walks a historical window forward one decision point at a time, runs the
REAL signal engine at each step against only the candles that had closed
by then (see `replay.py` for the no-look-ahead guarantee), resolves each
accepted signal against the real price at expiry, and aggregates the full
breakdown spec section 13 asks for.

Two properties this deliberately keeps:

1. It calls the same `build_signal()` the live collector calls. There is
   no separate "backtest version" of the strategy that could drift from
   what actually runs in production -- a classic way for backtest numbers
   to become quietly meaningless.
2. It resolves outcomes with the same rule as the live resolution job
   (`app/collector/resolution.py`): the close of the first M5 candle
   at/after expiry, equal price counting as DRAW. Backtest and live
   results are therefore directly comparable. Both share the same known
   approximation -- that candle's close is up to 5 minutes past the exact
   expiry moment -- documented in both places rather than silently
   differing.

What this is NOT: a claim that any result it produces is predictive.
Spec section 15 is explicit that accuracy figures only mean something
with sufficient verified unseen results. A backtest over a handful of
days of history is a smoke test of the rules, not evidence.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from app.backtesting import replay
from app.features.signal_engine import build_signal

logger = logging.getLogger(__name__)

# Enough closed history for EMA200 plus headroom. Slicing to this window
# keeps each step's indicator work bounded, so a long replay stays linear
# in the number of decision points rather than quadratic.
_MAX_LOOKBACK_BARS = 300


@dataclass
class BacktestOpportunity:
    """One evaluated decision point. `accepted` False means the engine saw
    a directional setup but rejected it on quality -- retained rather than
    discarded, per spec section 30."""
    asset: str
    generated_at: datetime
    direction: str
    technical_score: int
    grade: str
    market_regime: str
    session: str
    expiry_minutes: int | None
    entry_price: float | None
    accepted: bool
    result: str | None = None       # WON / LOST / DRAW, None if unresolved
    closing_price: float | None = None


@dataclass
class BacktestSummary:
    total_opportunities: int = 0
    accepted_signals: int = 0
    rejected_signals: int = 0
    wins: int = 0
    losses: int = 0
    draws: int = 0
    unresolved: int = 0
    win_rate: float = 0.0
    accuracy: float = 0.0
    signal_coverage: float = 0.0
    max_win_streak: int = 0
    max_loss_streak: int = 0
    performance_by_pair: list[dict] = field(default_factory=list)
    performance_by_expiry: list[dict] = field(default_factory=list)
    performance_by_session: list[dict] = field(default_factory=list)
    performance_by_regime: list[dict] = field(default_factory=list)
    performance_by_confidence_bucket: list[dict] = field(default_factory=list)
    opportunities: list[BacktestOpportunity] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def _score_bucket(score: int) -> str:
    if score >= 90:
        return "90-99"
    if score >= 80:
        return "80-89"
    if score >= 70:
        return "70-79"
    if score >= 60:
        return "60-69"
    return "<60"


def _decision_points(
    m5_candles: list[dict], start: datetime, end: datetime, step_minutes: int
) -> list[datetime]:
    """Every simulated 'now', aligned to real M5 candle closes so the
    engine is only ever asked to decide at a moment it could actually have
    decided live."""
    points: list[datetime] = []
    last_emitted: datetime | None = None
    for candle in m5_candles:
        close_time = replay.candle_close_time(candle, "M5")
        if close_time < start or close_time > end:
            continue
        if last_emitted is not None and (close_time - last_emitted) < timedelta(minutes=step_minutes):
            continue
        points.append(close_time)
        last_emitted = close_time
    return points


def run_backtest(
    candles_by_asset: dict[str, dict[str, list[dict]]],
    *,
    start: datetime,
    end: datetime,
    technical_score_threshold: int,
    expiry_filter: int | None = None,
    session_filter: str | None = None,
    regime_filter: str | None = None,
    step_minutes: int = 5,
) -> BacktestSummary:
    """Replays `start`..`end` for every asset in `candles_by_asset`.

    `candles_by_asset` is {asset: {timeframe: candles oldest-first}} --
    the full available history, INCLUDING bars after `end`, which are used
    only to resolve outcomes of signals generated before `end`. They can
    never influence a decision: every decision reads through
    `replay.slice_history`.
    """
    summary = BacktestSummary()

    for asset, history in candles_by_asset.items():
        m5 = history.get("M5", [])
        if not m5:
            summary.notes.append(f"{asset}: no M5 candle history stored — nothing to replay.")
            continue

        points = _decision_points(m5, start, end, step_minutes)
        if not points:
            summary.notes.append(
                f"{asset}: no M5 candles inside the requested window — "
                "the collector may not have been running then."
            )
            continue

        for as_of in points:
            sliced = replay.slice_history(history, as_of)
            # Bound the per-step work; the engine only ever needs recent history.
            sliced = {tf: candles[-_MAX_LOOKBACK_BARS:] for tf, candles in sliced.items()}

            decision = build_signal(
                asset, sliced, now=as_of, technical_score_threshold=technical_score_threshold
            )

            is_rejected_opportunity = decision.rejected_opportunity_direction is not None
            if decision.direction == "NO_TRADE" and not is_rejected_opportunity:
                # A genuine no-setup cycle: not a graded opportunity, so it
                # isn't counted in the accepted/rejected split (which would
                # inflate "rejected" with cycles that never had a candidate).
                continue

            if regime_filter and decision.market_regime != regime_filter:
                continue
            if session_filter and decision.session != session_filter:
                continue

            direction = decision.rejected_opportunity_direction or decision.direction
            expiry = decision.expiry_minutes
            if is_rejected_opportunity and expiry is None and decision.candidates:
                expiry = max(decision.candidates, key=lambda c: c.technical_score).expiry_minutes
            if expiry_filter is not None and expiry != expiry_filter:
                continue

            opportunity = BacktestOpportunity(
                asset=asset,
                generated_at=as_of,
                direction=direction,
                technical_score=decision.technical_score,
                grade=decision.grade,
                market_regime=decision.market_regime,
                session=decision.session,
                expiry_minutes=expiry,
                entry_price=decision.entry_price or None,
                accepted=not is_rejected_opportunity,
            )

            if opportunity.accepted and expiry is not None and opportunity.entry_price:
                expiry_at = as_of + timedelta(minutes=expiry)
                exit_candle = replay.first_candle_at_or_after(m5, expiry_at)
                if exit_candle is not None:
                    closing_price = float(exit_candle["close"])
                    entry_price = opportunity.entry_price
                    if closing_price == entry_price:
                        opportunity.result = "DRAW"
                    elif direction == "CALL":
                        opportunity.result = "WON" if closing_price > entry_price else "LOST"
                    else:
                        opportunity.result = "WON" if closing_price < entry_price else "LOST"
                    opportunity.closing_price = closing_price
                # else: history doesn't reach expiry -- left unresolved, never guessed

            summary.opportunities.append(opportunity)

    _aggregate(summary)
    return summary


def _aggregate(summary: BacktestSummary) -> None:
    opportunities = sorted(summary.opportunities, key=lambda o: o.generated_at)
    summary.opportunities = opportunities

    accepted = [o for o in opportunities if o.accepted]
    summary.total_opportunities = len(opportunities)
    summary.accepted_signals = len(accepted)
    summary.rejected_signals = len(opportunities) - len(accepted)
    summary.wins = sum(1 for o in accepted if o.result == "WON")
    summary.losses = sum(1 for o in accepted if o.result == "LOST")
    summary.draws = sum(1 for o in accepted if o.result == "DRAW")
    summary.unresolved = sum(1 for o in accepted if o.result is None)

    decided = summary.wins + summary.losses
    summary.win_rate = round(summary.wins / decided * 100, 2) if decided else 0.0
    # accuracy == win_rate here: with no calibrated model there is no second,
    # different notion of "correct" to separate them. Kept as its own field
    # because the schema and spec both name it.
    summary.accuracy = summary.win_rate
    summary.signal_coverage = (
        round(summary.accepted_signals / summary.total_opportunities * 100, 2)
        if summary.total_opportunities else 0.0
    )

    run_type: str | None = None
    run_length = 0
    for o in accepted:
        if o.result not in ("WON", "LOST"):
            continue
        if o.result == run_type:
            run_length += 1
        else:
            run_type = o.result
            run_length = 1
        if run_type == "WON":
            summary.max_win_streak = max(summary.max_win_streak, run_length)
        else:
            summary.max_loss_streak = max(summary.max_loss_streak, run_length)

    summary.performance_by_pair = _bucket(accepted, lambda o: o.asset)
    summary.performance_by_expiry = _bucket(accepted, lambda o: f"{o.expiry_minutes}m" if o.expiry_minutes else "—")
    summary.performance_by_session = _bucket(accepted, lambda o: o.session)
    summary.performance_by_regime = _bucket(accepted, lambda o: o.market_regime)
    summary.performance_by_confidence_bucket = _bucket(accepted, lambda o: _score_bucket(o.technical_score))

    if summary.unresolved:
        summary.notes.append(
            f"{summary.unresolved} accepted signal(s) had no stored candle at their expiry "
            "and are counted as unresolved rather than guessed — usually the tail end of the window."
        )
    if decided == 0 and summary.accepted_signals:
        summary.notes.append("No accepted signal resolved to a win or loss — accuracy figures are not meaningful yet.")


def _bucket(opportunities: list[BacktestOpportunity], key) -> list[dict]:
    buckets: dict[str, dict] = {}
    for o in opportunities:
        label = key(o)
        b = buckets.setdefault(label, {"label": label, "signals": 0, "wins": 0, "losses": 0, "draws": 0, "accuracy": 0.0})
        b["signals"] += 1
        if o.result == "WON":
            b["wins"] += 1
        elif o.result == "LOST":
            b["losses"] += 1
        elif o.result == "DRAW":
            b["draws"] += 1
    for b in buckets.values():
        decided = b["wins"] + b["losses"]
        b["accuracy"] = round(b["wins"] / decided * 100, 2) if decided else 0.0
    return sorted(buckets.values(), key=lambda b: b["label"])
