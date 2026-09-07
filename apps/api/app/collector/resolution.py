"""
Signal resolution (spec section 49): once a signal's expiry passes,
check the real closing price and mark it WON / LOST / DRAW. This is what
makes real accuracy figures on /dashboard/performance and
/dashboard/history possible -- there is no shortcut to a real number
here other than actually letting signals run to expiry and checking the
real price, which takes real time, not more code.

Equal-price handling: spec section 49 calls this "a configurable result
rule" -- this implementation treats entry_price == closing_price as
DRAW for both CALL and PUT, the least surprising default.

Safe to call every poll cycle: a signal whose expiry has passed but for
which no real candle has been stored yet at/after that time is simply
left ACTIVE and picked up on a later call -- never resolved from a
guess.

SHADOW RESOLUTION
-----------------
`resolve_shadow_opportunities()` does the same thing for setups the engine
REJECTED. Without it the quality threshold is unfalsifiable: the system only
ever measures the trades it took, so it can never learn whether the setups it
turned down would have lost. If rejected setups win at the same rate as
accepted ones, the threshold is doing nothing -- and nothing in the system
would ever reveal that.

The counterfactual outcome is written to separate `shadow_*` columns and the
row's `status` stays REJECTED. Every real performance query filters on
`status in ('WON','LOST','DRAW')`, so shadow outcomes cannot leak into
reported accuracy by construction rather than by remembering to exclude them.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from app.features.outcome import outcome as _outcome
from app.schemas.candle import Asset, Timeframe
from app.storage import audit_repository as audit
from app.storage.candle_repository import _asset_id_map, fetch_first_candle_at_or_after
from app.storage.supabase_client import get_service_client

logger = logging.getLogger(__name__)


def _asset_symbol_by_id() -> dict[str, str]:
    return {asset_id: asset.value for asset, asset_id in _asset_id_map().items()}


def resolve_expired_signals() -> int:
    """Resolves every ACTIVE, directional signal whose expiry has passed
    and for which a real candle already exists at/after that time.
    Returns the count resolved."""
    client = get_service_client()
    now = datetime.now(timezone.utc)

    response = (
        client.table("signals")
        .select("id, asset_id, direction, entry_price, expiry_at")
        .eq("status", "ACTIVE")
        .in_("direction", ["CALL", "PUT"])
        .lt("expiry_at", now.isoformat())
        .execute()
    )
    rows = response.data or []
    if not rows:
        return 0

    symbol_by_id = _asset_symbol_by_id()
    resolved_count = 0

    for row in rows:
        symbol = symbol_by_id.get(row["asset_id"])
        if symbol is None or row["entry_price"] is None:
            continue

        # Broker-OTC instruments are absent from the Asset enum by design
        # (see schemas/candle.py) and are resolved by app.otc.repository
        # against their own series. Passing one to Asset() raises
        # ValueError, and because that happened INSIDE the loop it aborted
        # the whole pass -- so a single Deriv row left every real-market
        # signal unresolved and sitting ACTIVE indefinitely. One
        # out-of-scope row must never decide the fate of the rest.
        try:
            asset = Asset(symbol)
        except ValueError:
            continue
        expiry_at = datetime.fromisoformat(row["expiry_at"])

        found = fetch_first_candle_at_or_after(asset, Timeframe.M5, expiry_at)
        if found is None:
            continue  # no real candle yet at/after expiry -- try again next cycle
        candle, quote_source = found
        closing_price = float(candle.close)
        entry_price = float(row["entry_price"])

        result = _outcome(row["direction"], entry_price, closing_price)

        resolved_at = datetime.now(timezone.utc)
        client.table("signals").update({
            "status": result,
            "result": result,
            "closing_price": str(closing_price),
            "resolved_at": resolved_at.isoformat(),
        }).eq("id", row["id"]).execute()

        client.table("signal_results").insert({
            "signal_id": row["id"],
            "resolved_at": resolved_at.isoformat(),
            "result": result,
            "entry_price": str(entry_price),
            "closing_price": str(closing_price),
            "quote_source": quote_source,
        }).execute()

        resolved_count += 1

    if resolved_count:
        logger.info("resolved %d expired signal(s)", resolved_count)
        audit.record(
            audit.ACTION_SIGNALS_RESOLVED,
            target_table="signals",
            metadata={"resolved": resolved_count},
        )
    return resolved_count


def resolve_shadow_opportunities(limit: int = 500) -> int:
    """Scores REJECTED directional opportunities against the real price at the
    expiry they would have used. Returns the count resolved.

    This is the feedback loop that makes the quality threshold measurable.
    Each resolved row becomes a labelled example of "a setup we declined",
    which is also exactly the negative class a future meta-model needs and
    which the system was previously discarding.

    Never touches status or result -- only the shadow_* columns.
    """
    client = get_service_client()
    now = datetime.now(timezone.utc)

    response = (
        client.table("signals")
        .select("id, asset_id, direction, entry_price, expiry_at")
        .eq("status", "REJECTED")
        .in_("direction", ["CALL", "PUT"])
        .lt("expiry_at", now.isoformat())
        .is_("shadow_result", "null")
        .limit(limit)
        .execute()
    )
    rows = response.data or []
    if not rows:
        return 0

    symbol_by_id = _asset_symbol_by_id()
    resolved_count = 0

    for row in rows:
        symbol = symbol_by_id.get(row["asset_id"])
        if symbol is None or row["entry_price"] is None or row["expiry_at"] is None:
            continue

        found = fetch_first_candle_at_or_after(
            Asset(symbol), Timeframe.M5, datetime.fromisoformat(row["expiry_at"])
        )
        if found is None:
            continue  # history hasn't reached expiry yet -- retry next cycle

        candle, _quote_source = found
        closing_price = float(candle.close)
        entry_price = float(row["entry_price"])

        client.table("signals").update({
            "shadow_result": _outcome(row["direction"], entry_price, closing_price),
            "shadow_closing_price": str(closing_price),
            "shadow_resolved_at": now.isoformat(),
        }).eq("id", row["id"]).execute()

        resolved_count += 1

    if resolved_count:
        logger.info("shadow-resolved %d rejected opportunity(ies)", resolved_count)
        audit.record(
            audit.ACTION_SHADOW_RESOLVED,
            target_table="signals",
            metadata={"resolved": resolved_count},
        )
    return resolved_count
