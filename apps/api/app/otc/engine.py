"""
The evaluation entry point (spec Phase 13).

ONE function, used identically by the live collector and the backtester.
The previous engine had production and replay call the same builder but
assemble its inputs differently, and the difference was where the
lookahead crept in. Here the caller supplies closed candles and a
timestamp; the engine has no clock and no I/O of its own, which is what
makes replay and live provably identical rather than approximately so.

The flow is exactly the spec's:

    health -> warmup -> context -> regime -> routing -> strategies
      -> CALL/PUT -> contradiction -> no-trade filters -> entry timing
      -> decision
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime

from app.otc.config import CONFIG, OTC_SYMBOLS
from app.otc.features import build_context
from app.otc.filters import (
    entry_timing_failures,
    regime_failures,
    scoring_failures,
    warmup_failures,
)
from app.otc.health import MarketDataHealth
from app.otc.regime import UNKNOWN, classify
from app.otc.routing import strategies_for
from app.otc.signal import CategoryScores, Direction, OTCDecision, SignalStatus
from app.otc.strategies.base import SideScore, StrategyVerdict

logger = logging.getLogger(__name__)


def evaluate(
    symbol: str,
    candles_by_timeframe: dict[str, list[dict]],
    now: datetime,
    health: MarketDataHealth,
) -> OTCDecision:
    """One evaluation. Always returns a decision -- never None, never an
    exception for ordinary market conditions. A rejected setup is a
    first-class result carrying its full evidence (Phase 32)."""
    cfg = OTC_SYMBOLS.get(symbol)
    broker = cfg.broker if cfg else "UNKNOWN"
    expiry = cfg.expiry_seconds if cfg else CONFIG.expiry_seconds

    def reject(reasons: list[str], *, context=None, verdict=None, regime=UNKNOWN, regime_reason="") -> OTCDecision:
        call = verdict.call if verdict else SideScore()
        put = verdict.put if verdict else SideScore()
        return OTCDecision(
            symbol=symbol, broker=broker, generated_at=now,
            direction=Direction.NO_TRADE, status=SignalStatus.REJECTED,
            price=context.price if context else 0.0, expiry_seconds=expiry,
            regime=regime, regime_reason=regime_reason,
            strategy=verdict.name if verdict else None,
            call_score=call.total, put_score=put.total,
            call_categories=_categories(call), put_categories=_categories(put),
            reasons=list(call.reasons if call.total >= put.total else put.reasons),
            warnings=list(verdict.warnings) if verdict else [],
            rejection_reasons=reasons,
            feed_status=health.status.value,
        )

    # --- 1. feed health. No override exists, by design (Phase 53).
    if not health.may_signal:
        return reject([f"feed {health.status.value}: {health.reason}"])

    # --- 2. context and warmup
    context = build_context(symbol, now, candles_by_timeframe)
    warm = warmup_failures(context)
    if warm:
        return reject(warm, context=context)

    # --- 3. regime
    regime, regime_reason = classify(context)
    context = build_context(symbol, now, candles_by_timeframe, regime=regime)
    bad_regime = regime_failures(context)
    if bad_regime:
        return reject(bad_regime, context=context, regime=regime, regime_reason=regime_reason)

    # --- 4. routing and strategies
    strategies = strategies_for(regime)
    if not strategies:
        return reject(
            [f"no strategy is permitted in {regime}"],
            context=context, regime=regime, regime_reason=regime_reason,
        )

    verdicts = [s.evaluate(context) for s in strategies]

    # The BEST single strategy wins, rather than an average. Averaging two
    # strategies produces a number describing neither market, and destroys
    # the per-strategy accuracy Phase 36 needs to know which idea works.
    verdict = max(verdicts, key=lambda v: max(v.call_total, v.put_total))

    # --- 5. scoring gates (contradiction + threshold)
    failures = scoring_failures(verdict)
    if failures:
        return reject(failures, context=context, verdict=verdict, regime=regime, regime_reason=regime_reason)

    direction = verdict.leader
    assert direction is not None  # scoring_failures rejects a tie

    # --- 6. entry timing
    timing = entry_timing_failures(context, direction)
    if timing:
        return reject(timing, context=context, verdict=verdict, regime=regime, regime_reason=regime_reason)

    winner = verdict.call if direction == "CALL" else verdict.put
    return OTCDecision(
        symbol=symbol, broker=broker, generated_at=now,
        direction=Direction(direction), status=SignalStatus.ACTIVE,
        price=context.price, expiry_seconds=expiry,
        regime=regime, regime_reason=regime_reason,
        strategy=verdict.name,
        call_score=verdict.call_total, put_score=verdict.put_total,
        call_categories=_categories(verdict.call), put_categories=_categories(verdict.put),
        reasons=list(winner.reasons), warnings=list(verdict.warnings),
        rejection_reasons=[], feed_status=health.status.value,
        fingerprint=_fingerprint(symbol, direction, verdict, regime),
    )


def _categories(side: SideScore) -> CategoryScores:
    return CategoryScores(
        trend=side.trend, structure=side.structure, momentum=side.momentum,
        price_action=side.price_action, levels=side.levels,
        volatility=side.volatility, entry_timing=side.entry_timing,
    )


def _fingerprint(symbol: str, direction: str, verdict: StrategyVerdict, regime: str) -> str:
    """Identity of the SETUP, not of the moment (Phase 26).

    Scores are bucketed to the nearest 5 so that the same structure
    re-evaluated 30 seconds later, scoring 84 instead of 83, is recognised
    as the same setup and suppressed by the cooldown -- which is the entire
    point of having one.
    """
    parts = (
        symbol, direction, verdict.name, regime,
        str(round(verdict.call_total / 5) * 5),
        str(round(verdict.put_total / 5) * 5),
    )
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]
