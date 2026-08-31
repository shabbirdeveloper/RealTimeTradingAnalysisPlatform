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

EXPIRIES: tuple[int, ...] = (15, 30, 60)

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
DEFAULT_LABEL = "v1"


@dataclass(frozen=True)
class StrategyConfig:
    """Tuning knobs for one (asset, expiry) pair."""

    expiry_minutes: int
    min_technical_score: int = DEFAULT_MIN_TECHNICAL_SCORE
    allowed_regimes: frozenset[str] = ALL_REGIMES
    allowed_sessions: frozenset[str] = ALL_SESSIONS
    enabled: bool = True

    def __post_init__(self) -> None:
        if self.expiry_minutes not in EXPIRIES:
            raise ValueError(f"expiry_minutes must be one of {EXPIRIES}, got {self.expiry_minutes}")
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
            return f"{self.expiry_minutes}m expiry is disabled in the strategy config."
        if regime not in self.allowed_regimes:
            return (
                f"Regime {regime.replace('_', ' ').lower()} is not permitted for the "
                f"{self.expiry_minutes}m expiry under the current strategy config."
            )
        if session not in self.allowed_sessions:
            return (
                f"{session.replace('_', ' ').title()} session is not permitted for the "
                f"{self.expiry_minutes}m expiry under the current strategy config."
            )
        if technical_score < self.min_technical_score:
            return (
                f"Technical score {technical_score} is below the {self.min_technical_score} "
                f"minimum for the {self.expiry_minutes}m expiry."
            )
        return None


@dataclass(frozen=True)
class AssetStrategy:
    """The full rule set for one asset: one StrategyConfig per expiry, plus
    the label that names this generation of the rules."""

    asset: str
    label: str
    by_expiry: Mapping[int, StrategyConfig]

    def __post_init__(self) -> None:
        missing = [e for e in EXPIRIES if e not in self.by_expiry]
        if missing:
            raise ValueError(f"AssetStrategy for {self.asset} is missing expiries: {missing}")

    def for_expiry(self, expiry_minutes: int) -> StrategyConfig:
        return self.by_expiry[expiry_minutes]

    def with_min_score(self, score: int) -> "AssetStrategy":
        """Every expiry forced to the same minimum score. This is what the
        backtester's threshold sweep (spec section 32's 'minimum confidence'
        input) needs: vary one number, hold everything else fixed."""
        return replace(
            self,
            by_expiry={e: replace(c, min_technical_score=score) for e, c in self.by_expiry.items()},
        )


def default_strategy(asset: str, *, label: str = DEFAULT_LABEL) -> AssetStrategy:
    """The shipped rule set: identical to the engine's behaviour before this
    module existed. Every expiry at 78, every regime and session allowed."""
    return AssetStrategy(
        asset=asset,
        label=label,
        by_expiry={e: StrategyConfig(expiry_minutes=e) for e in EXPIRIES},
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
                "expiry": e,
                "min_technical_score": c.min_technical_score,
                "allowed_regimes": sorted(c.allowed_regimes),
                "allowed_sessions": sorted(c.allowed_sessions),
                "enabled": c.enabled,
            }
            for e, c in sorted(strategy.by_expiry.items())
        ],
    }
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
    stock = default_strategy(strategy.asset)
    notes: list[str] = []
    for expiry in EXPIRIES:
        cfg, base = strategy.for_expiry(expiry), stock.for_expiry(expiry)
        if not cfg.enabled:
            notes.append(f"{expiry}m disabled")
            continue
        if cfg.min_technical_score != base.min_technical_score:
            notes.append(f"{expiry}m min score {cfg.min_technical_score} (default {base.min_technical_score})")
        if cfg.allowed_regimes != base.allowed_regimes:
            notes.append(f"{expiry}m regimes limited to {', '.join(sorted(cfg.allowed_regimes))}")
        if cfg.allowed_sessions != base.allowed_sessions:
            notes.append(f"{expiry}m sessions limited to {', '.join(sorted(cfg.allowed_sessions))}")
    return notes


def strategy_from_rows(
    asset: str, rows: Iterable[Mapping], *, label: str = DEFAULT_LABEL
) -> AssetStrategy:
    """Builds an AssetStrategy by layering database overrides over the code
    defaults, one expiry at a time.

    Defaults are NOT seeded into the table on purpose. A seeded row is a
    second copy of the default, and the two drift the moment either changes.
    An absent row means 'no override', which is unambiguous and needs no
    migration to stay in sync.

    Unknown expiries in the data are ignored rather than raised on: a row
    for an expiry this build no longer supports should not stop signal
    generation.
    """
    by_expiry = {e: StrategyConfig(expiry_minutes=e) for e in EXPIRIES}
    resolved_label = label

    # Sorted so the result does not depend on the order the caller happened to
    # fetch rows in. The label matters here: it is stored per row but names the
    # asset's rule set as a whole, so when rows disagree the lowest expiry wins
    # -- an arbitrary rule, but a FIXED one. A label that flip-flopped with
    # query order would make two identical configs look like two rule sets.
    # (Correctness never rests on this: the fingerprint covers every expiry.)
    for row in sorted(rows, key=lambda r: r.get("expiry_minutes") or 0, reverse=True):
        expiry = row.get("expiry_minutes")
        if expiry not in by_expiry:
            continue
        base = by_expiry[expiry]
        regimes = row.get("allowed_regimes")
        sessions = row.get("allowed_sessions")
        score = row.get("min_technical_score")
        enabled = row.get("enabled")
        by_expiry[expiry] = StrategyConfig(
            expiry_minutes=expiry,
            min_technical_score=int(score) if score is not None else base.min_technical_score,
            allowed_regimes=frozenset(regimes) if regimes else base.allowed_regimes,
            allowed_sessions=frozenset(sessions) if sessions else base.allowed_sessions,
            enabled=base.enabled if enabled is None else bool(enabled),
        )
        row_label = row.get("label")
        if row_label:
            resolved_label = str(row_label)

    return AssetStrategy(asset=asset, label=resolved_label, by_expiry=by_expiry)
