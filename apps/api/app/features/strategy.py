"""
Per-asset, per-expiry strategy configuration (the tuning apparatus).

WHY THIS EXISTS
---------------
Until now the entire engine ran on one module-level constant --
`TECHNICAL_SCORE_TAKE_THRESHOLD = 78` -- applied identically to all
fifteen asset/expiry combinations. Spec section 4 is explicit that the
same parameters should NOT be assumed to work equally well across
assets, and section 11 wants independent behaviour per expiry. With a
single constant, "raise the bar on XAUUSD 15m" was a code edit and a
redeploy, not a decision.

Worse, it was an *unattributable* decision. Signals generated under an
old rule set and a new one landed in the same table indistinguishable
from each other, so any before/after comparison silently mixed them --
which is how a tuning change gets credited with an improvement it did
not cause.

This module fixes both: configuration becomes data, and every decision
carries a version string identifying the exact rule set that produced
it.

DEFAULTS REPRODUCE TODAY'S BEHAVIOUR EXACTLY
--------------------------------------------
`default_strategy()` returns min_technical_score=78 for every expiry,
with every regime and every session allowed. The gates below therefore
never fire under defaults. That is deliberate: introducing the apparatus
must not, by itself, change a single signal. If it did, the two weeks of
history accumulating right now would be worthless as a baseline.

THE GATES CAN ONLY TIGHTEN, NEVER LOOSEN
----------------------------------------
`allowed_regimes` defaults to all six regimes, but the engine's existing
hard stand-down on HIGH_VOLATILITY and UNSTABLE stays in force above
this config and is not expressible here. So adding HIGH_VOLATILITY to
`allowed_regimes` does not enable trading in it. Config narrows the
engine's behaviour; it cannot widen it past a safety rule. Any future
knob added here must preserve that direction -- a configuration mistake
should cost signals, never produce reckless ones.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from typing import Iterable, Mapping

# Expiries are SECONDS everywhere in this module. The set an instrument
# actually offers comes from its TradingProfile -- real markets trade
# 15/30/60 minutes, broker-OTC trades 15-180 seconds, and one hardcoded tuple
# could not express both. This constant is only the real-market default, used
# where no instrument is in hand.
DEFAULT_EXPIRIES_SECONDS: tuple[int, ...] = (900, 1800, 3600)


def format_expiry(seconds: int) -> str:
    """Human-readable horizon. Seconds below a minute, minutes above -- a
    "3600s expiry" in an error message is needlessly hard to read."""
    if seconds < 60:
        return f"{seconds}s"
    if seconds % 60 == 0:
        return f"{seconds // 60}m"
    return f"{seconds // 60}m{seconds % 60}s"

# Spec section 7. NEWS_MODE is in the enum but never returned by the regime
# classifier (the news filter handles it upstream); it's listed so a config
# round-trip through the database can't lose it.
ALL_REGIMES: frozenset[str] = frozenset(
    {
        "TRENDING_UP",
        "TRENDING_DOWN",
        "RANGING",
        "HIGH_VOLATILITY",
        "LOW_VOLATILITY",
        "NEWS_MODE",
        "UNSTABLE",
    }
)

# Spec section 6's session features, as classified by structure.session_for_time().
ALL_SESSIONS: frozenset[str] = frozenset(
    {"ASIAN", "LONDON", "NEW_YORK", "LONDON_NY_OVERLAP"}
)

# The B-grade cutoff the engine has always used. Matches apps/web's
# gradeFromConfidence() so the frontend and the engine agree on what "B" means.
DEFAULT_MIN_TECHNICAL_SCORE = 78

# Human-readable label for the shipped rule set. An admin who tunes a config
# should bump this, but forgetting to is harmless -- see version_string().
#
# v2: the expiry/timeframe weighting became a computed ramp over the
# instrument's own ladder, replacing a hand-tuned table keyed on the literal
# values 15/30/60. That table could not express OTC's five second-scale
# horizons at all. The extremes are unchanged; the middle timeframes shift by
# up to 0.067, which is worth roughly half a technical-score point and can
# flip a setup sitting exactly on the threshold.
#
# The bump matters because the fingerprint covers CONFIG, not engine code --
# so without relabelling, signals scored under the old weighting and the new
# one would pool under one version, which is the precise failure the version
# stamp exists to prevent. Free to do now: the engine has never run, so there
# is no history to split.
DEFAULT_LABEL = "v2"

# Extracted from constants that were hardcoded in the engine. Changing a
# default here changes every fingerprint; changing an instance does not.
DEFAULT_MIN_TIMEFRAME_AGREEMENT = 3
DEFAULT_MIN_BIAS_VOTES = 2


@dataclass(frozen=True)
class StrategyConfig:
    """Tuning knobs for one (asset, expiry) pair."""

    expiry_seconds: int
    min_technical_score: int = DEFAULT_MIN_TECHNICAL_SCORE
    allowed_regimes: frozenset[str] = ALL_REGIMES
    allowed_sessions: frozenset[str] = ALL_SESSIONS
    enabled: bool = True

    def __post_init__(self) -> None:
        if self.expiry_seconds <= 0:
            raise ValueError(f"expiry_seconds must be positive, got {self.expiry_seconds}")
        if not 0 <= self.min_technical_score <= 100:
            raise ValueError(f"min_technical_score must be 0-100, got {self.min_technical_score}")
        unknown_regimes = set(self.allowed_regimes) - ALL_REGIMES
        if unknown_regimes:
            raise ValueError(f"unknown regimes in allowed_regimes: {sorted(unknown_regimes)}")
        unknown_sessions = set(self.allowed_sessions) - ALL_SESSIONS
        if unknown_sessions:
            raise ValueError(f"unknown sessions in allowed_sessions: {sorted(unknown_sessions)}")

    def rejection_reason(self, *, regime: str, session: str, technical_score: int) -> str | None:
        """None when this expiry is tradeable under the config, otherwise a
        trader-readable explanation of which gate stopped it.

        Order matters: the *structural* gates (disabled, regime, session)
        are checked before the score gate, because "we don't trade this
        expiry during the Asian session" is a more useful thing to read
        than "scored 74, needed 78" when both are true.
        """
        if not self.enabled:
            return f"{format_expiry(self.expiry_seconds)} expiry is disabled in the strategy config."
        if regime not in self.allowed_regimes:
            return (
                f"Regime {regime.replace('_', ' ').lower()} is not permitted for the "
                f"{format_expiry(self.expiry_seconds)} expiry under the current strategy config."
            )
        if session not in self.allowed_sessions:
            return (
                f"{session.replace('_', ' ').title()} session is not permitted for the "
                f"{format_expiry(self.expiry_seconds)} expiry under the current strategy config."
            )
        if technical_score < self.min_technical_score:
            return (
                f"Technical score {technical_score} is below the {self.min_technical_score} "
                f"minimum for the {format_expiry(self.expiry_seconds)} expiry."
            )
        return None


@dataclass(frozen=True)
class AssetStrategy:
    """The full rule set for one asset: one StrategyConfig per expiry, plus
    the label that names this generation of the rules."""

    asset: str
    label: str
    by_expiry: Mapping[int, StrategyConfig]

    # How many of the four timeframes must point the same way before a
    # direction is even proposed. Asset-level rather than per-expiry: the
    # timeframe read does not change with the horizon being considered.
    #
    # 3 of 4 is where this started, and it is the gate that stops the large
    # majority of cycles -- so it is also the least evidence-backed number
    # in the system. Making it a parameter is what lets gate_sweep.py
    # measure the alternatives instead of arguing about them.
    min_timeframe_agreement: int = DEFAULT_MIN_TIMEFRAME_AGREEMENT

    # How many of a timeframe's five voters (EMA20/50, EMA200, RSI, MACD,
    # swing structure) must agree before that timeframe commits to a
    # direction at all. Below this it reads NEUTRAL -- and a NEUTRAL vote
    # can never contribute to agreement above, so this number silently
    # governs the one above it.
    min_bias_votes: int = DEFAULT_MIN_BIAS_VOTES

    def __post_init__(self) -> None:
        if not self.by_expiry:
            raise ValueError(f"AssetStrategy for {self.asset} offers no expiries")

    @property
    def expiries(self) -> tuple[int, ...]:
        return tuple(sorted(self.by_expiry))

    def for_expiry(self, expiry_seconds: int) -> StrategyConfig:
        return self.by_expiry[expiry_seconds]

    def with_gates(self, *, agreement: int | None = None, bias_votes: int | None = None) -> "AssetStrategy":
        """Vary the two gate knobs, hold everything else fixed. The sweep's
        counterpart to with_min_score()."""
        return replace(
            self,
            min_timeframe_agreement=self.min_timeframe_agreement if agreement is None else agreement,
            min_bias_votes=self.min_bias_votes if bias_votes is None else bias_votes,
        )

    def with_min_score(self, score: int) -> "AssetStrategy":
        """Every expiry forced to the same minimum score. This is what the
        backtester's threshold sweep (spec section 32's 'minimum confidence'
        input) needs: vary one number, hold everything else fixed."""
        return replace(
            self,
            by_expiry={e: replace(c, min_technical_score=score) for e, c in self.by_expiry.items()},
        )


def default_strategy(
    asset: str, *, label: str = DEFAULT_LABEL, expiries: tuple[int, ...] | None = None
) -> AssetStrategy:
    """The shipped rule set: every expiry at 78, every regime and session
    allowed. For real markets this is identical to the engine's behaviour
    before this module existed.

    `expiries` comes from the instrument's TradingProfile. It defaults to the
    real-market set so callers that predate profiles keep working.
    """
    expiries = expiries or DEFAULT_EXPIRIES_SECONDS
    return AssetStrategy(
        asset=asset,
        label=label,
        by_expiry={e: StrategyConfig(expiry_seconds=e) for e in expiries},
    )


# ---------------------------------------------------------------------------
# Version stamping
# ---------------------------------------------------------------------------

def _canonical(strategy: AssetStrategy) -> str:
    """A stable, order-independent serialization of the effective rules.

    Sets are sorted so two identical configs never fingerprint differently
    because of dict/set iteration order, which would fragment a sample for
    no reason. The asset symbol is included: two assets sharing identical
    numbers are still separate rule sets, and merging their histories would
    be exactly the kind of pooling spec section 4 warns against.
    """
    payload = {
        "asset": strategy.asset,
        "expiries": [
            {
                "expiry_seconds": e,
                "min_technical_score": c.min_technical_score,
                "allowed_regimes": sorted(c.allowed_regimes),
                "allowed_sessions": sorted(c.allowed_sessions),
                "enabled": c.enabled,
            }
            for e, c in sorted(strategy.by_expiry.items())
        ],
    }
    # Gate knobs are recorded ONLY when they differ from the defaults.
    #
    # These parameters were extracted from constants that were already
    # baked into the engine, so a strategy sitting at the defaults is the
    # same rule set that produced the existing history -- and it must keep
    # the same fingerprint, or extracting a constant would silently split
    # a sample in two and make past and present results unppoolable for no
    # reason. Any non-default value is a genuinely different rule set and
    # does change the fingerprint.
    if strategy.min_timeframe_agreement != DEFAULT_MIN_TIMEFRAME_AGREEMENT:
        payload["min_timeframe_agreement"] = strategy.min_timeframe_agreement
    if strategy.min_bias_votes != DEFAULT_MIN_BIAS_VOTES:
        payload["min_bias_votes"] = strategy.min_bias_votes

    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def fingerprint(strategy: AssetStrategy) -> str:
    """Six hex characters over the canonical rules. Short enough to read in a
    table cell, wide enough (~16.7M values) that an accidental collision
    between two hand-edited configs is not a practical concern."""
    return hashlib.sha256(_canonical(strategy).encode("utf-8")).hexdigest()[:6]


def version_string(strategy: AssetStrategy) -> str:
    """What gets stamped on every signal, e.g. 'v1:a3f9c2'.

    The label is for humans; the fingerprint is what actually guarantees
    attribution. An admin who edits a threshold and forgets to bump the
    label still gets a new version string, so old and new results can never
    be pooled by accident. That asymmetry is intentional: forgetting to
    change a label should cost clarity, never correctness.

    It is asset-scoped and covers all three expiries together. Tuning only
    the 60m config therefore also starts a fresh 15m sample for that asset,
    which over-splits slightly -- but over-splitting is the safe error.
    The alternative, per-expiry fingerprints, risks merging rows that were
    produced under different rules the moment a change has cross-expiry
    effects.
    """
    return f"{strategy.label}:{fingerprint(strategy)}"


def summarize_overrides(strategy: AssetStrategy) -> list[str]:
    """Human-readable list of every way this strategy differs from the
    shipped defaults. Empty list means "running stock rules" -- which is
    worth being able to state positively, rather than inferring it from an
    absence of warnings."""
    stock = default_strategy(strategy.asset, expiries=strategy.expiries)
    notes: list[str] = []
    for expiry in strategy.expiries:
        cfg, base = strategy.for_expiry(expiry), stock.for_expiry(expiry)
        label = format_expiry(expiry)
        if not cfg.enabled:
            notes.append(f"{label} disabled")
            continue
        if cfg.min_technical_score != base.min_technical_score:
            notes.append(f"{label} min score {cfg.min_technical_score} (default {base.min_technical_score})")
        if cfg.allowed_regimes != base.allowed_regimes:
            notes.append(f"{label} regimes limited to {', '.join(sorted(cfg.allowed_regimes))}")
        if cfg.allowed_sessions != base.allowed_sessions:
            notes.append(f"{label} sessions limited to {', '.join(sorted(cfg.allowed_sessions))}")
    return notes


def row_expiry_seconds(row: Mapping) -> int | None:
    """The horizon a config row applies to, in seconds.

    Rows may carry either column. `expiry_seconds` wins when present;
    `expiry_minutes` is the pre-OTC spelling and is converted. Reading them in
    the other order would let a stale 15 (minutes) shadow a real 15 (seconds)
    and silently apply a 15-minute rule to a 15-second horizon.
    """
    seconds = row.get("expiry_seconds")
    if seconds is not None:
        return int(seconds)
    minutes = row.get("expiry_minutes")
    return int(minutes) * 60 if minutes is not None else None


def strategy_from_rows(
    asset: str,
    rows: Iterable[Mapping],
    *,
    label: str = DEFAULT_LABEL,
    expiries: tuple[int, ...] | None = None,
) -> AssetStrategy:
    """Builds an AssetStrategy by layering database overrides over the code
    defaults, one expiry at a time.

    Defaults are NOT seeded into the table on purpose. A seeded row is a
    second copy of the default, and the two drift the moment either changes.
    An absent row means 'no override', which is unambiguous and needs no
    migration to stay in sync.

    `expiries` comes from the instrument's TradingProfile, so an OTC
    instrument gets its second-scale horizons and a real-market one gets its
    minute-scale ones. Rows naming an expiry outside that set are ignored
    rather than raised on: a leftover row for a horizon this instrument no
    longer offers should not stop signal generation.
    """
    expiries = expiries or DEFAULT_EXPIRIES_SECONDS
    by_expiry = {e: StrategyConfig(expiry_seconds=e) for e in expiries}
    resolved_label = label

    # Sorted so the result does not depend on the order the caller happened to
    # fetch rows in. The label matters here: it is stored per row but names the
    # asset's rule set as a whole, so when rows disagree the shortest expiry
    # wins -- an arbitrary rule, but a FIXED one. A label that flip-flopped
    # with query order would make two identical configs look like two rule
    # sets. (Correctness never rests on this: the fingerprint covers every
    # expiry.)
    def sort_key(row: Mapping) -> int:
        return row_expiry_seconds(row) or 0

    for row in sorted(rows, key=sort_key, reverse=True):
        expiry = row_expiry_seconds(row)
        if expiry not in by_expiry:
            continue
        base = by_expiry[expiry]
        regimes = row.get("allowed_regimes")
        sessions = row.get("allowed_sessions")
        score = row.get("min_technical_score")
        enabled = row.get("enabled")
        by_expiry[expiry] = StrategyConfig(
            expiry_seconds=expiry,
            min_technical_score=int(score) if score is not None else base.min_technical_score,
            allowed_regimes=frozenset(regimes) if regimes else base.allowed_regimes,
            allowed_sessions=frozenset(sessions) if sessions else base.allowed_sessions,
            enabled=base.enabled if enabled is None else bool(enabled),
        )
        row_label = row.get("label")
        if row_label:
            resolved_label = str(row_label)

    return AssetStrategy(asset=asset, label=resolved_label, by_expiry=by_expiry)
