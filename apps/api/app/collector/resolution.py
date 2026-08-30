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
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

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
        asset = Asset(symbol)
        expiry_at = datetime.fromisoformat(row["expiry_at"])

        found = fetch_first_candle_at_or_after(asset, Timeframe.M5, expiry_at)
        if found is None:
            continue  # no real candle yet at/after expiry -- try again next cycle
        candle, quote_source = found
        closing_price = float(candle.close)
        entry_price = float(row["entry_price"])

        if closing_price == entry_price:
            result = "DRAW"
        elif row["direction"] == "CALL":
            result = "WON" if closing_price > entry_price else "LOST"
        else:  # PUT
            result = "WON" if closing_price < entry_price else "LOST"

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
