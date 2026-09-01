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
from datetime import datetime, timedelta, timezone

from app.features import structure as struct
from app.features.timeframe_bias import TimeframeBias, bias_for_timeframe
from app.features.regime import classify_regime
from app.market_data.closed_bars import interval_seconds
from app.instruments import FeedDescriptor, assert_feed_matches_instrument
from app.news.blackout import BlackoutConfig, EconomicEvent, evaluate_blackout
from app.features.strategy import (
    AssetStrategy,
    default_strategy,
    summarize_overrides,
    version_string,
)

EXPIRIES = (15, 30, 60)

# Kept as a module constant because the backtester, the tests and the admin UI
# all need to name "the shipped default" somewhere. The live threshold now
# comes from app.features.strategy per (asset, expiry) -- this is only its
# default value. See strategy.py for why that indirection exists.
TECHNICAL_SCORE_TAKE_THRESHOLD = 78  # matches apps/web's gradeFromConfidence() B cutoff

# How old the newest M5 candle may be before the engine refuses to decide.
# Spec section 42 requires signal generation to pause on stale data.
#
# Three closed M5 bars. Tight enough that a stalled collector, a provider
# outage, or a market gap is caught within ~15 minutes; loose enough to
# tolerate one missed poll without going dark. Deliberately NOT derived from
# the poll interval -- data freshness is a property of the market feed, not
# of how often we happen to ask for it.
MAX_CANDLE_AGE_MINUTES = 15


@dataclass(frozen=True)
class ExpiryCandidate:
    expiry_minutes: int
    direction: str
    technical_score: int
    grade: str  # "B" | "REJECTED" -- never higher without calibrated confidence
    # Which gate declined this expiry, in the strategy config's own words.
    # None on an accepted candidate. Recorded rather than discarded because
    # "60m was declined: Asian session not permitted" and "60m was declined:
    # scored 71" call for completely different tuning responses, and after
    # the fact the score alone cannot tell them apart.
    rejection_reason: str | None = None


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
    # The exact rule set that produced this decision, e.g. "v1:a3f9c2".
    # Stamped on every stored signal so results from different rule sets are
    # never pooled. See strategy.version_string().
    strategy_version: str = ""
    # Which feed priced the candles behind this decision, and what the
    # instrument actually is. Spec Phase 2: every signal must record its data
    # provenance, so a result can never be scored against a different series
    # than the one it was generated from.
    data_source: str = ""
    market_type: str = ""
    # Set only when a directional bias existed (spec section 30: "rejected
    # opportunities") but no expiry cleared the B-grade threshold -- e.g.
    # "Potential CALL, REJECTED". Distinguishes an admin-only rejected
    # opportunity from a genuine, user-visible NO_TRADE (conflicting
    # timeframes, insufficient data, or an unstable/high-vol regime) where
    # no directional bias ever existed. See signal_repository.py.
    rejected_opportunity_direction: str | None = None


def _staleness_reason(
    m5_candles: list[dict], now: datetime, max_age_minutes: int,
    entry_timeframe: str = "M5",
) -> str | None:
    """None when the newest candle is fresh enough to decide on, otherwise a
    trader-readable explanation of why it isn't.

    Measured from the candle's CLOSE (open_time + one interval), not its open --
    a bar that opened 6 minutes ago closed 1 minute ago and is perfectly
    current. Measuring from open_time would reject healthy data.
    """
    if not m5_candles:
        return "No M5 candles available — cannot analyse."

    newest_open = m5_candles[-1].get("open_time")
    if newest_open is None:
        return "Newest candle has no timestamp — cannot establish data freshness."
    if newest_open.tzinfo is None:
        raise ValueError("candle open_time must be timezone-aware (UTC)")

    close_time = newest_open + timedelta(seconds=interval_seconds(entry_timeframe))
    age_minutes = (now - close_time).total_seconds() / 60

    if age_minutes > max_age_minutes:
        return (
            f"Market data is stale — newest candle closed {int(age_minutes)} min ago "
            f"(limit {max_age_minutes} min). Signal generation paused until the feed recovers."
        )
    return None


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
    *,
    strategy: AssetStrategy | None = None,
    feed: FeedDescriptor | None = None,
    technical_score_threshold: int | None = None,
    economic_events: list[EconomicEvent] | None = None,
    calendar_available: bool = False,
    blackout_config: BlackoutConfig | None = None,
    max_candle_age_minutes: int = MAX_CANDLE_AGE_MINUTES,
) -> SignalDecision:
    """`strategy` is the per-expiry rule set for this asset (thresholds,
    permitted regimes, permitted sessions). Omit it and the shipped
    defaults apply, which reproduce this engine's behaviour before the
    strategy config existed -- introducing the apparatus changes no
    decision by itself. Live callers pass the asset's stored config;
    `build_signal` itself stays pure, doing no I/O, so the backtester can
    call it thousands of times per sweep.

    `technical_score_threshold` overrides the minimum score on every expiry
    at once. It exists so the backtester can sweep it (spec section 32's
    "minimum confidence" input) without duplicating any of this logic.
    Live callers should leave it unset -- a threshold that only holds up in
    a backtest is exactly the kind of curve-fit this project is supposed to
    catch, not ship.

    News protection (spec section 8): pass `economic_events` plus
    `calendar_available=True` when a real calendar feed is configured. The
    two are separate on purpose -- an empty event list with
    `calendar_available=False` means "we have no calendar", which must
    keep warning that news is unscreened, while an empty list with
    `calendar_available=True` genuinely means "nothing is scheduled".
    Collapsing them would make an unprotected system look protected.
    """
    # Provenance gate (see app/instruments.py). The danger is not the symbol,
    # it is a mismatch: pricing a broker-generated series with a public-market
    # feed produces a confident, graded signal about a series the user is not
    # trading. Raising here (rather than returning NO_TRADE) makes it a loud
    # configuration error instead of a quiet, plausible-looking one.
    #
    # `feed=None` keeps every existing real-market caller working, but an OTC
    # instrument must state its provenance or be refused -- OTC is fail-closed
    # because for OTC, provenance is the ONLY thing separating a real signal
    # from a fiction that looks identical.
    instrument = assert_feed_matches_instrument(asset, feed)

    strategy = strategy or default_strategy(asset)
    if technical_score_threshold is not None:
        strategy = strategy.with_min_score(technical_score_threshold)
    # Computed once, before any return path, so every decision this call can
    # produce -- including the early NO_TRADE exits -- carries the same stamp.
    # A signal that fell out of a stale-data or news gate is still evidence
    # about the rule set that was in force, and losing its attribution would
    # bias the recorded sample toward the cycles that happened to reach the
    # end of the function.
    stamp = version_string(strategy)

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

    # Two separate lists, joined only at the return.
    #
    # `warnings` is why THIS decision came out the way it did. `standing` is a
    # permanent caveat about the platform. They used to share one list with the
    # standing caveats first -- which meant warnings[0] was the same boilerplate
    # on every decision, and warnings[0] is exactly what the dashboard cards,
    # the analyzer's "Reason:" line and the deduplication fingerprint all read.
    # So every NO_TRADE explained itself as "meta model not available" instead
    # of naming its actual blocker, and two decisions blocked for entirely
    # different reasons deduplicated into one row.
    warnings: list[str] = []
    standing: list[str] = [
        "Meta trade/no-trade model not available yet (Phase 6) — this decision is technical-score-only.",
    ]

    # ---- Staleness gate (spec section 42) --------------------------------
    # Every indicator below is computed from these candles, and entry_price is
    # the newest close. If that data is old, the whole decision describes a
    # market that no longer exists -- and it would still render as a fully
    # graded signal. The frontend shows a freshness badge, which makes an
    # ungated engine actively misleading: the UI implies a check the engine
    # never performed.
    stale_reason = _staleness_reason(m5_candles, now, max_candle_age_minutes)
    if stale_reason is not None:
        warnings.append(stale_reason)
        return SignalDecision(
            asset=asset, direction="NO_TRADE", technical_score=0, grade="REJECTED",
            expiry_minutes=None, market_regime="UNSTABLE", regime_reason=stale_reason,
            entry_price=entry_price, session=session,
            reasons=["Market data is not fresh enough to analyse."],
            warnings=warnings + standing, timeframes=timeframes, candidates=[], generated_at=now, strategy_version=stamp, data_source=feed.name if feed else "", market_type=instrument.market_type.value,
        )

    blackout = evaluate_blackout(economic_events or [], asset, now, blackout_config)
    if not calendar_available:
        # A standing caveat, not a property of this setup: it is equally true
        # of every decision until a feed is configured.
        standing.append(
            "No economic calendar feed is configured — high-impact news is NOT being screened. "
            "Check the calendar yourself before trading."
        )

    if blackout.active:
        # A news blackout overrides everything: spec section 8 pauses signal
        # generation outright rather than scoring through it.
        warnings.append(blackout.reason or "High-impact news window active — signal generation paused.")
        return SignalDecision(
            asset=asset, direction="NO_TRADE", technical_score=0, grade="REJECTED", expiry_minutes=None,
            market_regime="NEWS_MODE", regime_reason=blackout.reason or "High-impact news window.",
            entry_price=entry_price, session=session,
            reasons=["Signal generation paused around a high-impact news release."],
            # Timeframes are still reported: during a pause the trader can
            # see what the market looks like, they just get no signal.
            warnings=warnings + standing, timeframes=timeframes, candidates=[], generated_at=now, strategy_version=stamp, data_source=feed.name if feed else "", market_type=instrument.market_type.value,
        )

    insufficient = [t.timeframe for t in timeframes if t.insufficient_data]
    if insufficient:
        warnings.append(f"Not enough real candle history yet on {', '.join(insufficient)} — analysis will sharpen as more real candles accumulate.")
        return SignalDecision(
            asset=asset, direction="NO_TRADE", technical_score=0, grade="REJECTED", expiry_minutes=None,
            market_regime=regime, regime_reason=regime_reason, entry_price=entry_price, session=session,
            reasons=["Insufficient real history to analyze this asset yet."], warnings=warnings + standing,
            timeframes=timeframes, candidates=[], generated_at=now, strategy_version=stamp, data_source=feed.name if feed else "", market_type=instrument.market_type.value,
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
            reasons=["Market conditions not strong enough for a high-quality setup."], warnings=warnings + standing,
            timeframes=timeframes, candidates=[], generated_at=now, strategy_version=stamp, data_source=feed.name if feed else "", market_type=instrument.market_type.value,
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
        score = int(round(max(0.0, min(99.0, score))))

        # The strategy config gets the final say on whether this expiry is
        # tradeable. It can only decline -- there is no path here by which a
        # config turns a low score into an accepted signal, and the regime
        # stand-down above has already run and cannot be overridden from
        # configuration. See strategy.py: config narrows, never widens.
        cfg = strategy.for_expiry(expiry)
        reason = cfg.rejection_reason(regime=regime, session=session, technical_score=score)
        candidates.append(
            ExpiryCandidate(
                expiry_minutes=expiry,
                direction=proposed_direction,
                technical_score=score,
                grade="REJECTED" if reason else "B",
                rejection_reason=reason,
            )
        )

    eligible = [c for c in candidates if c.grade != "REJECTED"]
    best = max(eligible, key=lambda c: c.technical_score) if eligible else None

    if best is None:
        # Report each expiry's actual blocker. The old message named the score
        # threshold unconditionally, which becomes a false explanation the
        # moment a session or regime gate is what actually declined the setup.
        blockers = "; ".join(
            c.rejection_reason for c in candidates if c.rejection_reason
        ) or "No expiry cleared the strategy config."
        warnings.append(f"No expiry accepted — {blockers}")
        return SignalDecision(
            asset=asset, direction="NO_TRADE", technical_score=max(c.technical_score for c in candidates),
            grade="REJECTED", expiry_minutes=None, market_regime=regime, regime_reason=regime_reason,
            entry_price=entry_price, session=session,
            reasons=["Directional bias present but no expiry scored high enough to act on."], warnings=warnings + standing,
            timeframes=timeframes, candidates=candidates, generated_at=now, strategy_version=stamp, data_source=feed.name if feed else "", market_type=instrument.market_type.value,
            rejected_opportunity_direction=proposed_direction,
        )

    h4, h1 = tf_by_name["H4"], tf_by_name["H1"]
    if h4.bias == h1.bias == target_bias:
        reasons.append(f"H4 and H1 both {h4.bias.lower()} — trend alignment confirmed.")
    reasons.append(f"{len(aligned)}/4 timeframes aligned {('bullish' if proposed_direction == 'CALL' else 'bearish')}.")
    reasons.append(f"Market regime: {regime.replace('_', ' ').lower()} — {regime_reason}")
    overrides = summarize_overrides(strategy)
    if overrides:
        # Not a warning: a tightened config is the system working as intended.
        # But it must be visible, or a signal produced under hand-tuned rules
        # is indistinguishable from one produced under the shipped ones.
        reasons.append(f"Strategy overrides in force ({stamp}): {'; '.join(overrides)}.")
    if h1_structure.bos:
        reasons.append("H1 structure confirms with a break of structure in the same direction." if (
            (proposed_direction == "CALL" and h1_structure.resistance and entry_price >= h1_structure.resistance) or
            (proposed_direction == "PUT" and h1_structure.support and entry_price <= h1_structure.support)
        ) else "H1 shows a break of structure (direction not yet confirmed against this setup).")

    return SignalDecision(
        asset=asset, direction=proposed_direction, technical_score=best.technical_score, grade=best.grade,
        expiry_minutes=best.expiry_minutes, market_regime=regime, regime_reason=regime_reason,
        entry_price=entry_price, session=session, reasons=reasons, warnings=warnings + standing,
        timeframes=timeframes, candidates=candidates, generated_at=now, strategy_version=stamp, data_source=feed.name if feed else "", market_type=instrument.market_type.value,
    )
