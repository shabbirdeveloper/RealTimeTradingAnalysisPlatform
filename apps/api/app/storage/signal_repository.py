"""
Writes signal decisions into `signals` (spec sections 9/30/37). A new row
is inserted every poll cycle -- signals are a time series of decisions,
not a single mutable "current signal" record, so history naturally
accumulates for the history/performance pages once those are wired up.

Status mapping (see the note on `SignalDecision.rejected_opportunity_direction`
in signal_engine.py for the reasoning):
  - A genuine NO_TRADE (conflicting timeframes, insufficient history, or an
    unstable/high-volatility regime) -> status ACTIVE, direction NO_TRADE.
    This is a first-class, user-visible result (spec section 18).
  - A real CALL/PUT that cleared the B-grade threshold -> status ACTIVE.
  - A directional bias that never cleared the B-grade threshold -> status
    REJECTED, direction set to the *potential* CALL/PUT (spec section 30's
    "Potential CALL ... REJECTED" example). RLS keeps REJECTED rows
    admin-only.
Never WON/LOST/DRAW here -- that's the separate resolution job (spec
section 49), not this write.

DEDUPLICATION
-------------
This used to insert a row on every poll cycle. One setup persisting for an
hour became six "independent" signals, each resolved against nearly the same
price -- which does not just bloat the table, it corrupts every accuracy
figure, because the confidence intervals downstream assume independent
trials. Six correlated copies of one outcome make the sample look six times
larger than it is, narrowing the interval toward a conclusion the evidence
does not support.

So a row is written only when the decision MATERIALLY changes. An unchanged
decision updates `last_evaluated_at` instead, which keeps "NO TRADE since
14:20" truthful while still recording that the engine is alive and looking.
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timedelta, timezone

from app.features.decision_identity import fingerprint as _fingerprint
from app.features.decision_identity import primary_note as _primary_note
from app.features.signal_engine import SignalDecision
from app.schemas.candle import Asset
from app.storage.candle_repository import _asset_id_map
from app.storage.supabase_client import get_service_client


def _timeframes_snapshot(decision: SignalDecision) -> list[dict]:
    return [
        {"timeframe": t.timeframe, "bias": t.bias, "strength": t.strength, "notes": t.notes}
        for t in decision.timeframes
    ]


def _candidates_snapshot(decision: SignalDecision) -> list[dict]:
    return [asdict(c) for c in decision.candidates]


def _latest_signal_row(client, asset_id: str) -> dict | None:
    response = (
        client.table("signals")
        .select("id, direction, grade, expiry_minutes, market_regime, status, "
                "expiry_at, reasons, warnings")
        .eq("asset_id", asset_id)
        .order("generated_at", desc=True)
        .limit(1)
        .execute()
    )
    rows = response.data or []
    return rows[0] if rows else None


def _touch(client, signal_id: str, now: datetime) -> None:
    client.table("signals").update(
        {"last_evaluated_at": now.isoformat()}
    ).eq("id", signal_id).execute()


def insert_signal(asset: Asset, decision: SignalDecision) -> str | None:
    asset_id = _asset_id_map()[asset]
    client = get_service_client()

    generated_at = decision.generated_at.astimezone(timezone.utc)

    if decision.rejected_opportunity_direction is not None:
        direction = decision.rejected_opportunity_direction
        status = "REJECTED"
    else:
        direction = decision.direction
        status = "ACTIVE"

    # A rejected opportunity has no chosen expiry, but it needs one to be
    # shadow-resolved later -- otherwise there is no moment at which to ask
    # "would this have won?", and the quality threshold stays unfalsifiable.
    # Use the expiry the engine would have picked: its highest-scoring
    # candidate.
    expiry_minutes = decision.expiry_minutes
    if expiry_minutes is None and decision.rejected_opportunity_direction and decision.candidates:
        expiry_minutes = max(decision.candidates, key=lambda c: c.technical_score).expiry_minutes

    expiry_at = (
        (generated_at + timedelta(minutes=expiry_minutes)).isoformat()
        if expiry_minutes is not None
        else None
    )

    row = {
        "asset_id": asset_id,
        "direction": direction,
        "generated_at": generated_at.isoformat(),
        "last_evaluated_at": generated_at.isoformat(),
        "entry_price": str(decision.entry_price) if decision.entry_price else None,
        "expiry_minutes": expiry_minutes,
        "expiry_at": expiry_at,
        "technical_score": decision.technical_score,
        "raw_probability": None,  # Phase 6 (ML) not built -- never fabricated
        "calibrated_confidence": None,
        "grade": decision.grade,
        "market_regime": decision.market_regime,
        "model_version_id": None,
        "status": status,
        "session": decision.session,
        "reasons": decision.reasons,
        "warnings": decision.warnings,
        "timeframes_snapshot": {
            "timeframes": _timeframes_snapshot(decision),
            "candidates": _candidates_snapshot(decision),
            "regime_reason": decision.regime_reason,
        },
    }

    # ---- deduplication ---------------------------------------------------
    latest = _latest_signal_row(client, asset_id)
    if latest is not None:
        # An unexpired directional signal is still live. Opening a second one
        # for the same asset is not a new opportunity -- the trader is already
        # in (or has already passed on) this move. The database enforces this
        # too, via a partial unique index, so a race can't slip past.
        if (
            latest["status"] == "ACTIVE"
            and latest["direction"] in ("CALL", "PUT")
            and latest.get("expiry_at")
            and datetime.fromisoformat(latest["expiry_at"]) > generated_at
        ):
            _touch(client, latest["id"], generated_at)
            return latest["id"]

        # Otherwise: same decision as last time -> just record that we looked.
        if _fingerprint(
            latest["direction"], latest["grade"], latest["expiry_minutes"],
            latest["market_regime"],
            _primary_note(latest.get("reasons"), latest.get("warnings")),
        ) == _fingerprint(
            direction, decision.grade, decision.expiry_minutes,
            decision.market_regime,
            _primary_note(decision.reasons, decision.warnings),
        ):
            _touch(client, latest["id"], generated_at)
            return latest["id"]

    response = client.table("signals").insert(row).execute()
    rows = response.data or []
    return rows[0]["id"] if rows else None
