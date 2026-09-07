"""
Persisting an OTCDecision (spec Phases 31, 32).

Writes to the EXISTING `signals` table rather than a parallel `otc_signals`.
The table already carries `data_source` and `market_type`, so broker-OTC
rows are separable by a WHERE clause; a second table would fork every
query, every RLS policy and every analytics function to achieve the same
separation the column already gives.

Accepted and rejected decisions are the same row with a different status.
Phase 32 wants rejected candidates analysable later -- which is only cheap
if rejection is a field rather than a different code path that discards
the evidence on the way out.
"""

from __future__ import annotations

import logging
from dataclasses import asdict
from datetime import datetime, timedelta, timezone

from app.otc.signal import Direction, OTCDecision, SignalStatus

# Storage imports are deliberately deferred into the functions that need
# them. The scoring rules in this module are pure -- given a row and a
# price series they decide WON/LOST/DRAW -- and importing them should not
# require pydantic, a Supabase client, or credentials. Tests exercise the
# rules directly; only the I/O paths pay for the dependency.

logger = logging.getLogger(__name__)

# The engine's identity, stored on every row. Any accuracy comparison must
# group on this: rows produced by different rules cannot be pooled without
# crediting a tuning change with an improvement it did not cause.
STRATEGY_VERSION = "otc-v1"


def store_decision(decision: OTCDecision) -> str | None:
    """Insert one decision. Returns the row id, or None if it was
    suppressed or could not be written.

    Never raises for ordinary storage trouble: one failed write must not
    stop the collector, because a stopped collector produces silence, and
    silence is indistinguishable from a quiet market.
    """
    from app.storage.candle_repository import asset_id_for_symbol
    from app.storage.supabase_client import get_service_client

    try:
        client = get_service_client()
        asset_id = asset_id_for_symbol(decision.symbol)
    except Exception as exc:
        logger.warning("%s: cannot resolve asset for storage: %s", decision.symbol, exc)
        return None

    generated_at = decision.generated_at.astimezone(timezone.utc)

    if decision.is_signal and _in_cooldown(client, asset_id, decision, generated_at):
        logger.info(
            "%s: %s suppressed by cooldown (same setup %s)",
            decision.symbol, decision.direction.value, decision.fingerprint,
        )
        return None

    row = {
        "asset_id": asset_id,
        # A rejected setup keeps the direction it WOULD have taken, so the
        # rejected-setup dataset can later be asked whether the filters
        # helped or hurt. Storing NO_TRADE here would throw that away.
        "direction": decision.direction.value if decision.is_signal else _leaning(decision),
        "generated_at": generated_at.isoformat(),
        "last_evaluated_at": generated_at.isoformat(),
        "entry_price": str(decision.price) if decision.is_signal else None,
        # Legacy column: only ever (15, 30, 60). A 300-second expiry written
        # as 5 is rejected by its CHECK constraint and takes the whole row
        # with it -- which silently discarded the first real Deriv decision.
        "expiry_minutes": None,
        "expiry_seconds": decision.expiry_seconds,
        "expiry_at": decision.expiry_at.isoformat(),
        "technical_score": decision.score,
        "call_score": decision.call_score,
        "put_score": decision.put_score,
        # Phase 45 rules out ML for now, so these stay NULL rather than
        # being filled with the technical score wearing a different name.
        "raw_probability": None,
        "calibrated_confidence": None,
        # NOT NULL, and its vocabulary is a probability claim: A++ means
        # 90%+ CONFIDENCE, which requires a calibrated model we do not have
        # (spec sections 10 and 45). So every signal is graded B -- the
        # floor -- and the technical score beside it carries the quality.
        # Deriving A++ from a technical score would be exactly the "never
        # fake 90%" the spec forbids, dressed as a lookup table.
        "grade": "B" if decision.is_signal else "REJECTED",
        "market_regime": decision.regime,
        "strategy_version": STRATEGY_VERSION,
        "data_source": decision.broker,
        "market_type": "BROKER_OTC",
        "model_version_id": None,
        "status": decision.status.value,
        "session": None,
        "reasons": decision.reasons,
        "warnings": decision.warnings,
        "timeframes_snapshot": {
            "engine": STRATEGY_VERSION,
            "strategy": decision.strategy,
            "regime_reason": decision.regime_reason,
            "feed_status": decision.feed_status,
            "fingerprint": decision.fingerprint,
            "rejection_reasons": decision.rejection_reasons,
            "call_categories": asdict(decision.call_categories),
            "put_categories": asdict(decision.put_categories),
        },
    }

    try:
        result = client.table("signals").insert(row).execute()
    except Exception as exc:
        logger.warning("%s: signal insert failed: %s", decision.symbol, exc)
        return None

    rows = getattr(result, "data", None) or []
    signal_id = rows[0]["id"] if rows else None

    # Notify only on a stored SIGNAL. Two conditions, both load-bearing:
    # a rejected setup is not news, and a decision that failed to store
    # must not be announced -- a Telegram message for a row that does not
    # exist is worse than silence, because it will never appear in the
    # history the message implies it is part of.
    if signal_id and decision.is_signal:
        _notify(decision)

    return signal_id


def _notify(decision: OTCDecision) -> None:
    """Best-effort. A notification failure must never look like, or become,
    a storage failure -- the decision is already safely recorded, and the
    message is a convenience on top of it."""
    try:
        from app.notifications.telegram import notify_otc_signal

        if notify_otc_signal(decision):
            logger.info("[OTC_SIGNAL] %s %s notified", decision.symbol, decision.direction.value)
    except Exception:  # noqa: BLE001
        logger.exception("%s: notification failed", decision.symbol)


def _leaning(decision: OTCDecision) -> str:
    """Which way a rejected setup was leaning. Ties resolve to CALL only
    because the column is NOT NULL; the score pair beside it says the
    lean was meaningless, so nothing downstream should read this alone."""
    return "CALL" if decision.call_score >= decision.put_score else "PUT"


def _in_cooldown(client, asset_id: str, decision: OTCDecision, now: datetime) -> bool:
    """Phase 26. Suppress a repeat of the SAME setup, not merely a repeat
    of the same direction.

    The distinction matters: a market that genuinely turns, produces a new
    structure and signals the same way again is a second opportunity. The
    same structure re-scored 30 seconds later is not, and firing on it
    would emit ten identical CALLs from one move.
    """
    from app.otc.config import CONFIG

    since = (now - timedelta(seconds=CONFIG.cooldown_seconds)).isoformat()
    try:
        result = (
            client.table("signals")
            .select("id, direction, status, timeframes_snapshot")
            .eq("asset_id", asset_id)
            .eq("status", SignalStatus.ACTIVE.value)
            .gte("generated_at", since)
            .execute()
        )
    except Exception as exc:
        # Fail CLOSED. If we cannot tell whether this is a duplicate, the
        # safe answer is to suppress: a missed signal costs one opportunity,
        # a duplicate burst costs the user's trust in every signal.
        logger.warning("%s: cooldown check failed, suppressing: %s", decision.symbol, exc)
        return True

    for row in getattr(result, "data", None) or []:
        snapshot = row.get("timeframes_snapshot") or {}
        if snapshot.get("fingerprint") and snapshot["fingerprint"] == decision.fingerprint:
            return True
        if row.get("direction") == decision.direction.value:
            return True
    return False


def resolve_due_signals(now: datetime | None = None) -> int:
    """Phase 30. Score every ACTIVE signal whose expiry has passed, against
    the SAME series that generated it.

    The price comes from our own stored candles for that instrument, not
    from any external source -- scoring a Deriv synthetic against real
    EUR/USD would be meaningless, and the provenance columns exist so that
    mistake is impossible to make silently.
    """
    from app.storage.candle_repository import fetch_recent_otc_candles
    from app.storage.supabase_client import get_service_client

    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    try:
        client = get_service_client()
        # The symbol is joined in because the candle reader is keyed by
        # symbol, not asset id. Passing the id straight through returned no
        # candles and every expired signal stayed ACTIVE forever -- silence
        # that looks exactly like "nothing has expired yet".
        result = (
            client.table("signals")
            .select("id, asset_id, direction, entry_price, expiry_at, assets(symbol)")
            .eq("status", SignalStatus.ACTIVE.value)
            .eq("market_type", "BROKER_OTC")
            .lte("expiry_at", now.isoformat())
            .execute()
        )
    except Exception as exc:
        logger.warning("resolution query failed: %s", exc)
        return 0

    resolved = 0
    for row in getattr(result, "data", None) or []:
        outcome = _score(row, now, fetch_recent_otc_candles)
        if outcome is None:
            continue
        status, closing = outcome
        try:
            client.table("signals").update({
                "status": status,
                "result": status,
                "closing_price": str(closing) if closing is not None else None,
                "resolved_at": now.isoformat(),
            }).eq("id", row["id"]).execute()
            resolved += 1
        except Exception as exc:
            logger.warning("could not resolve signal %s: %s", row["id"], exc)
    return resolved


def _score(row: dict, now: datetime, fetch) -> tuple[str, float | None] | None:
    """CALL wins above entry, PUT wins below, equal is a DRAW (Phase 30).

    Returns None when no candle covers the expiry instant. That is NOT a
    loss and must never be recorded as one: an outcome we cannot observe
    is not an outcome the engine got wrong, and counting missing data as
    losses corrupts the win rate in the pessimistic direction just as
    surely as the reverse.
    """
    expiry_at = datetime.fromisoformat(row["expiry_at"])
    entry = float(row["entry_price"]) if row.get("entry_price") else None
    if entry is None:
        return (SignalStatus.INVALIDATED.value, None)

    asset = row.get("assets") or {}
    symbol = asset.get("symbol") if isinstance(asset, dict) else None
    if not symbol:
        return None
    try:
        candles = fetch(symbol, "S15", 400)
    except Exception:
        return None

    at_expiry = [c for c in candles if c["open_time"] <= expiry_at]
    if not at_expiry:
        return None
    # Guard against resolving from a bar far from the expiry instant: a
    # stale series would otherwise produce a confident, meaningless result.
    last = at_expiry[-1]
    if (expiry_at - last["open_time"]).total_seconds() > 120:
        return (SignalStatus.INVALIDATED.value, None)

    closing = float(last["close"])
    if closing == entry:
        return (SignalStatus.DRAW.value, closing)
    higher = closing > entry
    won = higher if row["direction"] == Direction.CALL.value else not higher
    return (SignalStatus.WON.value if won else SignalStatus.LOST.value, closing)
