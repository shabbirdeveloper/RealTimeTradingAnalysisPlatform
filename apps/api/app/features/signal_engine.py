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
from app.instruments import FeedDescriptor, TradingProfile, assert_feed_matches_instrument
from app.news.blackout import BlackoutConfig, EconomicEvent, evaluate_blackout
from app.features.strategy import (
    AssetStrategy,
    default_strategy,
    format_expiry,
    summarize_overrides,
    version_string,
)


# Kept as a module constant because the backtester, the tests and the admin UI
# all need to name "the shipped default" somewhere. The live threshold now
# comes from app.features.strategy per (asset, expiry) -- this is only its
# default value. See strategy.py for why that indirection exists.
TECHNICAL_SCORE_TAKE_THRESHOLD = 78  # matches apps/web's gradeFromConfidence() B cutoff

# Staleness limits now live on the instrument's TradingProfile
# (`max_data_age_seconds`), because the right limit is a property of the
# timeframe being traded: 15 minutes of staleness is a minor gap on an M5
# real-market ladder and an eternity on a 15-second OTC one. Both profiles
# use three closed entry bars.
#
# Kept as a module constant only so the backtester and tests can name the
# historical real-market value.
MAX_CANDLE_AGE_MINUTES = 15


@dataclass(frozen=True)
class DecisionCheck:
    """One gate the setup had to pass, and whether it did (spec Phase 26).

    Recorded for EVERY decision, not just rejections. A trader looking at a
    NO_TRADE card wants to know which gate stopped it and how close it came;
    a trader looking at an accepted signal wants to know what it cleared. The
    engine already evaluates all of this -- it just used to throw the working
    away and keep one sentence.
    """

    name: str          # "Multi-timeframe agreement"
    passed: bool
    detail: str        # "2 of 4 bullish — needs 3"
    # None when the gate has no meaningful numeric form (a news blackout).
    value: str | None = None
    required: str | None = None


@dataclass(frozen=True)
class ExpiryCandidate:
    expiry_seconds: int
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
    expiry_seconds: int | None
    market_regime: str
    regime_reason: str
    entry_price: float
    session: str
    reasons: list[str]
    warnings: list[str]
    timeframes: list[TimeframeBias]
    candidates: list[ExpiryCandidate]
    # Every gate this setup was put through, in order, with the first failure
    # marking where it stopped. This is the whole audit trail for a decision.
    checks: list[DecisionCheck]
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
    entry_candles: list[dict], now: datetime, max_age_minutes: float,
    entry_timeframe: str = "M5",
) -> str | None:
    """None when the newest candle is fresh enough to decide on, otherwise a
    trader-readable explanation of why it isn't.

    Measured from the candle's CLOSE (open_time + one interval), not its open --
    a bar that opened 6 minutes ago closed 1 minute ago and is perfectly
    current. Measuring from open_time would reject healthy data.
    """
    if not entry_candles:
        return f"No {entry_timeframe} candles available — cannot analyse."

    newest_open = entry_candles[-1].get("open_time")
    if newest_open is None:
        return "Newest candle has no timestamp — cannot establish data freshness."
    if newest_open.tzinfo is None:
        raise ValueError("candle open_time must be timezone-aware (UTC)")

    close_time = newest_open + timedelta(seconds=interval_seconds(entry_timeframe))
    age_minutes = (now - close_time).total_seconds() / 60

    if age_minutes > max_age_minutes:
        return (
            f"Market data is stale — newest candle closed {int(age_minutes)} min ago "
            f"(limit {max_age_minutes:.0f} min). Signal generation paused until the feed recovers."
        )
    return None


def _bias_label(direction: str) -> str:
    return {"CALL": "BULLISH", "PUT": "BEARISH"}.get(direction, "NEUTRAL")


def _expiry_weight(
    expiry_seconds: int, timeframe: str, profile: TradingProfile
) -> float:
    """How much a timeframe should count toward a given expiry.

    The shortest expiry on offer leans on the fastest timeframes; the longest
    leans on the slowest. Spec section 11's "independent model per expiry"
    idea, expressed as a weighting rule rather than a trained model (which
    doesn't exist yet).

    This used to be a lookup keyed on the literal values 15/30/60. That could
    not express OTC's five second-scale horizons at all, and any expiry not
    in the table silently fell through to the neutral weights. It is now
    computed from where the expiry sits in the profile's own range and where
    the timeframe sits in the profile's ladder, so it works for any instrument
    class without a table to keep in sync.
    """
    expiries = sorted(profile.expiries_seconds)
    ladder = profile.timeframes

    # 0.0 = shortest expiry offered, 1.0 = longest -- by RANK, not by value.
    #
    # Rank rather than linear interpolation on the numbers, because the
    # numbers are not evenly spaced: 1800s sits a third of the way between
    # 900 and 3600, so a value-based scale would quietly re-weight the
    # 30-minute expiry that has been running unchanged. Rank reproduces the
    # previous fast/mid/slow table exactly for real markets while still
    # generalising to OTC's five horizons.
    rank = expiries.index(expiry_seconds) if expiry_seconds in expiries else len(expiries) // 2
    horizon = 0.5 if len(expiries) == 1 else rank / (len(expiries) - 1)

    # 0.0 = slowest timeframe in the ladder, 1.0 = fastest.
    idx = ladder.index(timeframe)
    speed = idx / (len(ladder) - 1) if len(ladder) > 1 else 0.5

    # A short horizon favours fast timeframes and vice versa. The 0.4 spread
    # reproduces the old table's 0.6-1.4 range at the extremes.
    return 1.0 + 0.4 * (1.0 - 2.0 * horizon) * (2.0 * speed - 1.0)


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
    max_candle_age_minutes: float | None = None,
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

    profile = instrument.profile
    strategy = strategy or default_strategy(asset, expiries=profile.expiries_seconds)
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
        bias_for_timeframe(tf, candles_by_timeframe.get(tf, []), min_votes=strategy.min_bias_votes)
        for tf in profile.timeframes
    ]

    # Structure and regime come from the ladder's second-slowest rung: slow
    # enough to describe context, fast enough to still be responsive. On the
    # real-market ladder that is H1, exactly as before; on OTC it is M1.
    context_timeframe = profile.timeframes[1] if len(profile.timeframes) > 1 else profile.timeframes[0]
    h1_candles = candles_by_timeframe.get(context_timeframe, [])
    h1_structure = struct.classify_structure(h1_candles) if h1_candles else struct.StructureReading(
        sequence=None, bos=False, choch=False, support=None, resistance=None
    )
    regime, regime_reason = classify_regime(h1_candles, h1_structure) if h1_candles else ("UNSTABLE", "No H1 history yet.")

    entry_candles = candles_by_timeframe.get(profile.entry_timeframe, [])
    entry_price = float(entry_candles[-1]["close"]) if entry_candles else 0.0

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
    checks: list[DecisionCheck] = []
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
    def record(name: str, passed: bool, detail: str,
               value: str | None = None, required: str | None = None) -> None:
        checks.append(DecisionCheck(name=name, passed=passed, detail=detail,
                                    value=value, required=required))

    stale_reason = _staleness_reason(
        entry_candles, now,
        max_candle_age_minutes if max_candle_age_minutes is not None
        else profile.max_data_age_seconds / 60,
        profile.entry_timeframe,
    )
    record(
        "Data freshness", stale_reason is None,
        stale_reason or f"Newest {profile.entry_timeframe} candle is current.",
        required=f"under {profile.max_data_age_seconds // 60} min old",
    )
    if stale_reason is not None:
        warnings.append(stale_reason)
        return SignalDecision(
            asset=asset, direction="NO_TRADE", technical_score=0, grade="REJECTED",
            expiry_seconds=None, market_regime="UNSTABLE", regime_reason=stale_reason,
            entry_price=entry_price, session=session,
            reasons=["Market data is not fresh enough to analyse."],
            warnings=warnings + standing, timeframes=timeframes, candidates=[], checks=checks, generated_at=now, strategy_version=stamp, data_source=feed.name if feed else "", market_type=instrument.market_type.value,
        )

    blackout = evaluate_blackout(economic_events or [], asset, now, blackout_config)
    if not calendar_available:
        # A standing caveat, not a property of this setup: it is equally true
        # of every decision until a feed is configured.
        standing.append(
            "No economic calendar feed is configured — high-impact news is NOT being screened. "
            "Check the calendar yourself before trading."
        )

    record(
        "News window", not blackout.active,
        blackout.reason or ("No high-impact news nearby."
                            if calendar_available
                            else "No calendar feed configured — news is NOT screened."),
    )
    if blackout.active:
        # A news blackout overrides everything: spec section 8 pauses signal
        # generation outright rather than scoring through it.
        warnings.append(blackout.reason or "High-impact news window active — signal generation paused.")
        return SignalDecision(
            asset=asset, direction="NO_TRADE", technical_score=0, grade="REJECTED", expiry_seconds=None,
            market_regime="NEWS_MODE", regime_reason=blackout.reason or "High-impact news window.",
            entry_price=entry_price, session=session,
            reasons=["Signal generation paused around a high-impact news release."],
            # Timeframes are still reported: during a pause the trader can
            # see what the market looks like, they just get no signal.
            warnings=warnings + standing, timeframes=timeframes, candidates=[], checks=checks, generated_at=now, strategy_version=stamp, data_source=feed.name if feed else "", market_type=instrument.market_type.value,
        )

    insufficient = [t.timeframe for t in timeframes if t.insufficient_data]
    record(
        "History warm-up", not insufficient,
        f"Not enough history on {', '.join(insufficient)}." if insufficient
        else "All timeframes have enough history.",
        value=f"{len(timeframes) - len(insufficient)}/{len(timeframes)} ready",
    )
    if insufficient:
        warnings.append(f"Not enough real candle history yet on {', '.join(insufficient)} — analysis will sharpen as more real candles accumulate.")
        return SignalDecision(
            asset=asset, direction="NO_TRADE", technical_score=0, grade="REJECTED", expiry_seconds=None,
            market_regime=regime, regime_reason=regime_reason, entry_price=entry_price, session=session,
            reasons=["Insufficient real history to analyze this asset yet."], warnings=warnings + standing,
            timeframes=timeframes, candidates=[], checks=checks, generated_at=now, strategy_version=stamp, data_source=feed.name if feed else "", market_type=instrument.market_type.value,
        )

    bull_votes = sum(1 for t in timeframes if t.bias == "BULLISH")
    bear_votes = sum(1 for t in timeframes if t.bias == "BEARISH")

    needed = strategy.min_timeframe_agreement
    proposed_direction = "NO_TRADE"
    if bull_votes >= needed:
        proposed_direction = "CALL"
    elif bear_votes >= needed:
        proposed_direction = "PUT"

    # This is the gate that stops the overwhelming majority of cycles, so it
    # is the one worth showing a trader most precisely: not "conflicting" but
    # how many agreed and how many were needed.
    leading = max(bull_votes, bear_votes)
    record(
        "Multi-timeframe agreement", proposed_direction != "NO_TRADE",
        ", ".join(f"{t.timeframe} {t.bias.lower()}" for t in timeframes),
        value=f"{leading} of {len(timeframes)} agree",
        required=f"{needed} of {len(timeframes)}",
    )

    record(
        "Market regime", regime not in ("HIGH_VOLATILITY", "UNSTABLE"),
        regime_reason, value=regime.replace("_", " ").lower(),
    )
    if regime in ("HIGH_VOLATILITY", "UNSTABLE"):
        warnings.append(f"Market regime classified {regime} — standing down regardless of timeframe alignment.")
        proposed_direction = "NO_TRADE"

    if proposed_direction == "NO_TRADE":
        if regime not in ("HIGH_VOLATILITY", "UNSTABLE"):
            # Built from the profile's own ladder rather than naming H4/H1/
            # M15/M5, which do not exist on an OTC instrument.
            detail = ", ".join(f"{t.timeframe} {t.bias.lower()}" for t in timeframes)
            warnings.append(f"Timeframes conflicting: {detail}.")
        return SignalDecision(
            asset=asset, direction="NO_TRADE", technical_score=0, grade="REJECTED", expiry_seconds=None,
            market_regime=regime, regime_reason=regime_reason, entry_price=entry_price, session=session,
            reasons=["Market conditions not strong enough for a high-quality setup."], warnings=warnings + standing,
            timeframes=timeframes, candidates=[], checks=checks, generated_at=now, strategy_version=stamp, data_source=feed.name if feed else "", market_type=instrument.market_type.value,
        )

    target_bias = _bias_label(proposed_direction)
    aligned = [t for t in timeframes if t.bias == target_bias]
    avg_strength = sum(t.strength for t in timeframes) / len(timeframes)

    candidates: list[ExpiryCandidate] = []
    for expiry in strategy.expiries:
        weighted_strength = sum(
            t.strength * _expiry_weight(expiry, t.timeframe, profile) for t in timeframes
        ) / sum(_expiry_weight(expiry, t.timeframe, profile) for t in timeframes)
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
                expiry_seconds=expiry,
                direction=proposed_direction,
                technical_score=score,
                grade="REJECTED" if reason else "B",
                rejection_reason=reason,
            )
        )

    eligible = [c for c in candidates if c.grade != "REJECTED"]
    best = max(eligible, key=lambda c: c.technical_score) if eligible else None

    top = max(candidates, key=lambda c: c.technical_score)
    record(
        "Setup quality", best is not None,
        (f"Best expiry {format_expiry(best.expiry_seconds)} scored {best.technical_score}."
         if best else
         "; ".join(c.rejection_reason for c in candidates if c.rejection_reason)
         or "No expiry cleared the strategy config."),
        value=f"{top.technical_score}/100",
        required=f"{strategy.for_expiry(top.expiry_seconds).min_technical_score}/100",
    )

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
            grade="REJECTED", expiry_seconds=None, market_regime=regime, regime_reason=regime_reason,
            entry_price=entry_price, session=session,
            reasons=["Directional bias present but no expiry scored high enough to act on."], warnings=warnings + standing,
            timeframes=timeframes, candidates=candidates, checks=checks, generated_at=now, strategy_version=stamp, data_source=feed.name if feed else "", market_type=instrument.market_type.value,
            rejected_opportunity_direction=proposed_direction,
        )

    # The two slowest rungs carry trend context, whatever they are called on
    # this instrument: H4/H1 on a real-market ladder, M5/M1 on an OTC one.
    slow, mid = timeframes[0], timeframes[1]
    if slow.bias == mid.bias == target_bias:
        reasons.append(
            f"{slow.timeframe} and {mid.timeframe} both {slow.bias.lower()} — "
            "trend alignment confirmed."
        )
    reasons.append(f"{len(aligned)}/{len(timeframes)} timeframes aligned {('bullish' if proposed_direction == 'CALL' else 'bearish')}.")
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
        expiry_seconds=best.expiry_seconds, market_regime=regime, regime_reason=regime_reason,
        entry_price=entry_price, session=session, reasons=reasons, warnings=warnings + standing,
        timeframes=timeframes, candidates=candidates, checks=checks, generated_at=now, strategy_version=stamp, data_source=feed.name if feed else "", market_type=instrument.market_type.value,
    )
