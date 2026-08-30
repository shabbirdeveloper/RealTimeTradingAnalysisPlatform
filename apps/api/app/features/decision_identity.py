"""
What counts as "the same trading decision".

Extracted from the storage layer so it can be unit-tested without a database
or the supabase package -- the rule this encodes is a domain decision, not a
persistence detail, and it is the thing standing between clean statistics and
corrupted ones.

Background: the engine used to write a signal row every poll cycle. One setup
persisting for an hour became six "independent" signals resolved against
nearly the same price. Accuracy figures downstream assume independent trials,
so correlated duplicates make a sample look larger than it is and narrow the
confidence interval toward a conclusion the evidence doesn't support.
"""
from __future__ import annotations

# Fields that define a decision's identity. Notably ABSENT: technical_score.
# It drifts a point or two every cycle as the newest candle lands, and
# treating that drift as a new signal would defeat the entire purpose.
IDENTITY_FIELDS = ("direction", "grade", "expiry_minutes", "market_regime", "primary_note")

# The reason text is compared truncated: two NO_TRADEs whose explanations
# differ only in a trailing minute count ("news in 12 min" vs "in 11 min")
# are the same state, not a new one.
_NOTE_COMPARE_CHARS = 120


def primary_note(reasons: list[str] | None, warnings: list[str] | None) -> str:
    """The single line a trader would read first. Warnings outrank reasons --
    a NO_TRADE is explained by what blocked it, not by what was fine."""
    if warnings:
        return warnings[0]
    if reasons:
        return reasons[0]
    return ""


def fingerprint(
    direction: str,
    grade: str,
    expiry_minutes: int | None,
    market_regime: str,
    note: str,
) -> tuple:
    """Identity tuple for a decision. Equal fingerprints mean the state has
    not materially changed and no new row should be written.

    `market_regime` and `note` are included on purpose: a NO_TRADE that
    switches from "timeframes conflicting" to a news blackout is a genuinely
    different state a trader would want recorded, even though the direction
    and grade are unchanged.
    """
    return (direction, grade, expiry_minutes, market_regime, (note or "")[:_NOTE_COMPARE_CHARS])
