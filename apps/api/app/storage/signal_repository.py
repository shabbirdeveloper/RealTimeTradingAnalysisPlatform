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

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone

from app.features.decision_identity import fingerprint as _fingerprint
from app.features.decision_identity import primary_note as _primary_note
from app.features.signal_engine import SignalDecision
from app.schemas.candle import Asset
from app.storage.candle_repository import _asset_id_map
from app.storage.supabase_client import get_service_client


def _row_expiry_seconds(row: dict) -> int | None:
    """A stored row's horizon in seconds. `expiry_seconds` wins; the older
    `expiry_minutes` is converted. Reading them the other way round would let
    a legacy 15 (minutes) shadow a real 15 (seconds)."""
    seconds = row.get("expiry_seconds")
    if seconds is not None:
        return int(seconds)
    minutes = row.get("expiry_minutes")
    return int(minutes) * 60 if minutes is not None else None


def _timeframes_snapshot(decision: SignalDecision) -> list[dict]:
    return [
        {"timeframe": t.timeframe, "bias": t.bias, "strength": t.strength, "notes": t.notes}
        for t in decision.timeframes
    ]


def _candidates_snapshot(decision: SignalDecision) -> list[dict]:
    return [asdict(c) for c in decision.candidates]


def _checks_snapshot(decision: SignalDecision) -> list[dict]:
    """Spec Phase 26/27: the gates this setup passed and where it stopped.

    Stored with the signal rather than recomputed, because the market has
    moved on by the time anyone looks. A reason reconstructed later from
    current data would describe a different moment than the decision did.
    """
    return [asdict(c) for c in decision.checks]


def _latest_signal_row(client, asset_id: str) -> dict | None:
    response = (
        client.table("signals")
        .select("id, direction, grade, expiry_minutes, expiry_seconds, market_regime, "
                "status, expiry_at, reasons, warnings, strategy_version")
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


@dataclass(frozen=True)
class SignalWrite:
    """What actually happened to the database on this cycle.

    `created` distinguishes a genuinely new decision from a re-confirmation of
    a standing one. Callers that act on signals -- alerting above all -- need
    that: without it, an alert fires every poll for as long as a setup lasts,
    and an alert that repeats is one you learn to ignore.
    """

    signal_id: str | None
    created: bool
    direction: str
    status: str


def insert_signal(asset: Asset, decision: SignalDecision) -> SignalWrite:
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
    expiry_seconds = decision.expiry_seconds
    if expiry_seconds is None and decision.rejected_opportunity_direction and decision.candidates:
        expiry_seconds = max(decision.candidates, key=lambda c: c.technical_score).expiry_seconds

    expiry_at = (
        (generated_at + timedelta(seconds=expiry_seconds)).isoformat()
        if expiry_seconds is not None
        else None
    )

    # Both columns are written, and they mean different things.
    #
    # `expiry_seconds` is authoritative -- it is what the engine actually
    # decided, and the only column that can express a 15-second OTC horizon.
    # `expiry_minutes` is the pre-OTC spelling, still populated for
    # real-market signals so the existing frontend, admin tables and
    # performance queries keep working unchanged.
    #
    # It is left NULL for anything that is not a whole number of minutes
    # rather than rounded. A 15-second expiry rounded to 0 minutes is wrong,
    # and rounded to 1 minute is a four-fold lie about the horizon; a null
    # reads honestly as "this horizon is not expressible in this column".
    expiry_minutes = (
        expiry_seconds // 60
        if expiry_seconds is not None and expiry_seconds % 60 == 0
        else None
    )

    row = {
        "asset_id": asset_id,
        "direction": direction,
        "generated_at": generated_at.isoformat(),
        "last_evaluated_at": generated_at.isoformat(),
        "entry_price": str(decision.entry_price) if decision.entry_price else None,
        "expiry_minutes": expiry_minutes,
        "expiry_seconds": expiry_seconds,
        "expiry_at": expiry_at,
        "technical_score": decision.technical_score,
        # Both sides, so a stored decision stays explicable without
        # re-deriving it. score_difference is generated in the database.
        "call_score": decision.call_score,
        "put_score": decision.put_score,
        "raw_probability": None,  # Phase 6 (ML) not built -- never fabricated
        "calibrated_confidence": None,
        "grade": decision.grade,
        "market_regime": decision.market_regime,
        # Which rule set produced this row. Every accuracy comparison across
        # time must group on this -- rows with different values came from
        # different rules and pooling them would credit a tuning change with
        # an improvement it did not cause.
        "strategy_version": decision.strategy_version or None,
        # Which feed priced the candles behind this row, and what kind of
        # instrument it is. Spec Phase 2/18: resolution must score a signal
        # against the SAME series that generated it, and that is only
        # checkable if the series is recorded here.
        "data_source": decision.data_source or None,
        "market_type": decision.market_type or None,
        "model_version_id": None,
        "status": status,
        "session": decision.session,
        "reasons": decision.reasons,
        "warnings": decision.warnings,
        "timeframes_snapshot": {
            "timeframes": _timeframes_snapshot(decision),
            "candidates": _candidates_snapshot(decision),
            "checks": _checks_snapshot(decision),
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
            return SignalWrite(latest["id"], created=False, direction=direction, status=status)

        # Otherwise: same decision as last time -> just record that we looked.
        if _fingerprint(
            latest["direction"], latest["grade"], _row_expiry_seconds(latest),
            latest["market_regime"],
            _primary_note(latest.get("reasons"), latest.get("warnings")),
            latest.get("strategy_version") or "",
        ) == _fingerprint(
            direction, decision.grade, expiry_seconds,
            decision.market_regime,
            _primary_note(decision.reasons, decision.warnings),
            decision.strategy_version or "",
        ):
            _touch(client, latest["id"], generated_at)
            return SignalWrite(latest["id"], created=False, direction=direction, status=status)

    response = client.table("signals").insert(row).execute()
    rows = response.data or []
    return SignalWrite(
        rows[0]["id"] if rows else None, created=bool(rows),
        direction=direction, status=status,
    )
