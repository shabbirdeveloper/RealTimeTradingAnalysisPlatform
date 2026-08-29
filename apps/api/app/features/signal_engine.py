"""
Real, rule-based signal engine (spec sections 9-12): combines the real
per-timeframe bias, real market regime, and real structure into a
CALL / PUT / NO_TRADE decision with a genuinely-computed Technical Score.

What this deliberately does NOT do: it never invents a calibrated ML
confidence percentage or an A++/A+/A grade. Spec section 10 is explicit
that those percentages "must come from calibrated model outputs when ML
is enabled" and must never be faked -- and the ML pipeline (Phase 6:
XGBoost/LightGBM/calibration) hasn't been built yet, so `raw_probability`
and `calibrated_confidence` are always None here, and grade is capped at
B (or REJECTED) exactly like the frontend's own `gradeFromConfidence`
rule for the MODEL_NOT_READY case. Similarly, the meta trade/no-trade
model (spec section 12) doesn't exist yet -- its absence is stated as a
warning, not silently ignored, and it never blocks or approves a trade.

Indicator/structure/regime *weights* below (vote counts, the 78-point B
threshold, per-expiry emphasis) are a reasonable starting rule set, not
a backtested-optimal one -- validating and tuning them against real
historical outcomes is exactly what the backtesting engine (spec section
13, `/admin/backtesting`) is for once enough real signal history exists.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.features import structure as struct
from app.features.timeframe_bias import TimeframeBias, bias_for_timeframe
from app.features.regime import classify_regime

EXPIRIES = (15, 30, 60)
TECHNICAL_SCORE_TAKE_THRESHOLD = 78  # matches apps/web's gradeFromConfidence() B cutoff


@dataclass(frozen=True)
class ExpiryCandidate:
    expiry_minutes: int
    direction: str
    technical_score: int
    grade: str  # "B" | "REJECTED" -- never higher without calibrated confidence


@dataclass(frozen=True)
class SignalDecision:
    asset: str
    direction: str  # CALL | PUT | NO_TRADE
    technical_score: int
    grade: str
    expiry_minutes: int | None
    market_regime: str
    regime_reason: str
    entry_price: float
    session: str
    reasons: list[str]
    warnings: list[str]
    timeframes: list[TimeframeBias]
    candidates: list[ExpiryCandidate]
    generated_at: datetime
    # Set only when a directional bias existed (spec section 30: "rejected
    # opportunities") but no expiry cleared the B-grade threshold -- e.g.
    # "Potential CALL, REJECTED". Distinguishes an admin-only rejected
    # opportunity from a genuine, user-visible NO_TRADE (conflicting
    # timeframes, insufficient data, or an unstable/high-vol regime) where
    # no directional bias ever existed. See signal_repository.py.
    rejected_opportunity_direction: str | None = None


def _bias_label(direction: str) -> str:
    return {"CALL": "BULLISH", "PUT": "BEARISH"}.get(direction, "NEUTRAL")


def _expiry_weight(expiry_minutes: int, timeframe: str) -> float:
    """15m entries lean on the fast timeframes (M5/M15); 60m entries lean
    on the slow ones (H1/H4). This is the same "which timeframe matters
    most for which expiry" idea as spec section 11's independent-model
    architecture, expressed as a weighting rule rather than a separate
    trained model per expiry (those don't exist yet either).
    """
    fast = {"M5": 1.4, "M15": 1.2, "H1": 0.8, "H4": 0.6}
    slow = {"M5": 0.6, "M15": 0.8, "H1": 1.2, "H4": 1.4}
    mid = {"M5": 1.0, "M15": 1.0, "H1": 1.0, "H4": 1.0}
    table = fast if expiry_minutes == 15 else slow if expiry_minutes == 60 else mid
    return table[timeframe]


def build_signal(
    asset: str,
    candles_by_timeframe: dict[str, list[dict]],
    now: datetime | None = None,
) -> SignalDecision:
    now = now or datetime.now(timezone.utc)
    session = struct.session_for_time(now)

    timeframes: list[TimeframeBias] = [
        bias_for_timeframe(tf, candles_by_timeframe.get(tf, []))
        for tf in ("H4", "H1", "M15", "M5")
    ]
    tf_by_name = {t.timeframe: t for t in timeframes}

    h1_candles = candles_by_timeframe.get("H1", [])
    h1_structure = struct.classify_structure(h1_candles) if h1_candles else struct.StructureReading(
        sequence=None, bos=False, choch=False, support=None, resistance=None
    )
    regime, regime_reason = classify_regime(h1_candles, h1_structure) if h1_candles else ("UNSTABLE", "No H1 history yet.")

    m5_candles = candles_by_timeframe.get("M5", [])
    entry_price = float(m5_candles[-1]["close"]) if m5_candles else 0.0

    reasons: list[str] = []
    warnings: list[str] = [
        "Meta trade/no-trade model not available yet (Phase 6) — this decision is technical-score-only.",
        "Economic calendar filter not active yet (Phase 7) — high-impact news is not being screened automatically.",
    ]

    insufficient = [t.timeframe for t in timeframes if t.insufficient_data]
    if insufficient:
        warnings.insert(0, f"Not enough real candle history yet on {', '.join(insufficient)} — analysis will sharpen as more real candles accumulate.")
        return SignalDecision(
            asset=asset, direction="NO_TRADE", technical_score=0, grade="REJECTED", expiry_minutes=None,
            market_regime=regime, regime_reason=regime_reason, entry_price=entry_price, session=session,
            reasons=["Insufficient real history to analyze this asset yet."], warnings=warnings,
            timeframes=timeframes, candidates=[], generated_at=now,
        )

    bull_votes = sum(1 for t in timeframes if t.bias == "BULLISH")
    bear_votes = sum(1 for t in timeframes if t.bias == "BEARISH")

    proposed_direction = "NO_TRADE"
    if bull_votes >= 3:
        proposed_direction = "CALL"
    elif bear_votes >= 3:
        proposed_direction = "PUT"

    if regime in ("HIGH_VOLATILITY", "UNSTABLE"):
        warnings.append(f"Market regime classified {regime} — standing down regardless of timeframe alignment.")
        proposed_direction = "NO_TRADE"

    if proposed_direction == "NO_TRADE":
        h4, h1, m15, m5 = tf_by_name["H4"], tf_by_name["H1"], tf_by_name["M15"], tf_by_name["M5"]
        if regime not in ("HIGH_VOLATILITY", "UNSTABLE"):
            warnings.append(
                f"Timeframes conflicting: H4 {h4.bias.lower()}, H1 {h1.bias.lower()}, "
                f"M15 {m15.bias.lower()}, M5 {m5.bias.lower()}."
            )
        return SignalDecision(
            asset=asset, direction="NO_TRADE", technical_score=0, grade="REJECTED", expiry_minutes=None,
            market_regime=regime, regime_reason=regime_reason, entry_price=entry_price, session=session,
            reasons=["Market conditions not strong enough for a high-quality setup."], warnings=warnings,
            timeframes=timeframes, candidates=[], generated_at=now,
        )

    target_bias = _bias_label(proposed_direction)
    aligned = [t for t in timeframes if t.bias == target_bias]
    avg_strength = sum(t.strength for t in timeframes) / len(timeframes)

    candidates: list[ExpiryCandidate] = []
    for expiry in EXPIRIES:
        weighted_strength = sum(t.strength * _expiry_weight(expiry, t.timeframe) for t in timeframes) / sum(
            _expiry_weight(expiry, t.timeframe) for t in timeframes
        )
        score = weighted_strength * 0.7 + len(aligned) * 6
        if regime in ("TRENDING_UP", "TRENDING_DOWN"):
            score += 6
        elif regime == "RANGING":
            score -= 8
        score = round(max(0.0, min(99.0, score)))
        grade = "B" if score >= TECHNICAL_SCORE_TAKE_THRESHOLD else "REJECTED"
        candidates.append(ExpiryCandidate(expiry_minutes=expiry, direction=proposed_direction, technical_score=int(score), grade=grade))

    eligible = [c for c in candidates if c.grade != "REJECTED"]
    best = max(eligible, key=lambda c: c.technical_score) if eligible else None

    if best is None:
        warnings.append("No expiry cleared the technical-score threshold for a B grade or better.")
        return SignalDecision(
            asset=asset, direction="NO_TRADE", technical_score=max(c.technical_score for c in candidates),
            grade="REJECTED", expiry_minutes=None, market_regime=regime, regime_reason=regime_reason,
            entry_price=entry_price, session=session,
            reasons=["Directional bias present but no expiry scored high enough to act on."], warnings=warnings,
            timeframes=timeframes, candidates=candidates, generated_at=now,
            rejected_opportunity_direction=proposed_direction,
        )

    h4, h1 = tf_by_name["H4"], tf_by_name["H1"]
    if h4.bias == h1.bias == target_bias:
        reasons.append(f"H4 and H1 both {h4.bias.lower()} — trend alignment confirmed.")
    reasons.append(f"{len(aligned)}/4 timeframes aligned {('bullish' if proposed_direction == 'CALL' else 'bearish')}.")
    reasons.append(f"Market regime: {regime.replace('_', ' ').lower()} — {regime_reason}")
    if h1_structure.bos:
        reasons.append("H1 structure confirms with a break of structure in the same direction." if (
            (proposed_direction == "CALL" and h1_structure.resistance and entry_price >= h1_structure.resistance) or
            (proposed_direction == "PUT" and h1_structure.support and entry_price <= h1_structure.support)
        ) else "H1 shows a break of structure (direction not yet confirmed against this setup).")

    return SignalDecision(
        asset=asset, direction=proposed_direction, technical_score=best.technical_score, grade=best.grade,
        expiry_minutes=best.expiry_minutes, market_regime=regime, regime_reason=regime_reason,
        entry_price=entry_price, session=session, reasons=reasons, warnings=warnings,
        timeframes=timeframes, candidates=candidates, generated_at=now,
    )
