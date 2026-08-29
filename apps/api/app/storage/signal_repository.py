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
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import timedelta, timezone

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

    expiry_at = (
        (generated_at + timedelta(minutes=decision.expiry_minutes)).isoformat()
        if decision.expiry_minutes is not None
        else None
    )

    row = {
        "asset_id": asset_id,
        "direction": direction,
        "generated_at": generated_at.isoformat(),
        "entry_price": str(decision.entry_price) if decision.entry_price else None,
        "expiry_minutes": decision.expiry_minutes,
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

    response = client.table("signals").insert(row).execute()
    rows = response.data or []
    return rows[0]["id"] if rows else None
