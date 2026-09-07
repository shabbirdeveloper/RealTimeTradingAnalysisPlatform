"""
POST /api/signals/evaluate — run one evaluation right now.

WHY THIS IS NOT A "GET ME A SIGNAL" BUTTON
------------------------------------------
It runs the SAME evaluate() the scheduler runs, on the same closed bars,
and returns whatever that returns — which is usually NO TRADE. It cannot
be pressed until a CALL appears, and the response says so explicitly:
`bar_unchanged` is true when the entry bar has not closed since the last
evaluation, meaning the inputs are identical and so is the answer.

That field exists because the obvious failure mode of an on-demand button
is that it becomes a slot-machine handle. A trader who presses it twenty
times and takes the one CALL it eventually produces has not found a
signal; they have found the moment the market drifted, and they have
thrown away the selectivity that is the whole product. Making "nothing
has changed" a first-class part of the response is the cheapest defence
against that.

The endpoint stores its decision like any other, so an on-demand
evaluation appears in the same history and the same accuracy figures. A
decision that counted only when convenient would corrupt both.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from app.config import get_settings
from app.otc.config import OTC_SYMBOLS, REAL_MARKET_PROFILE, profile_for
from app.otc.signal import OTCDecision

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/signals", tags=["signals"])


def _serialise(decision: OTCDecision, *, bar_unchanged: bool, evaluated_at: datetime) -> dict:
    return {
        "symbol": decision.symbol,
        "direction": decision.direction.value,
        "status": decision.status.value,
        "isSignal": decision.is_signal,
        "callScore": decision.call_score,
        "putScore": decision.put_score,
        "difference": decision.difference,
        "score": decision.score,
        "regime": decision.regime,
        "regimeReason": decision.regime_reason,
        "strategy": decision.strategy,
        "feedStatus": decision.feed_status,
        "entryPrice": decision.entry_price,
        "price": decision.price,
        "expirySeconds": decision.expiry_seconds,
        "expiryAt": decision.expiry_at.isoformat() if decision.is_signal else None,
        "reasons": decision.reasons,
        "warnings": decision.warnings,
        "rejectionReasons": decision.rejection_reasons,
        "evaluatedAt": evaluated_at.isoformat(),
        # True when the entry bar has not closed since the previous
        # evaluation: the inputs are identical, so pressing again cannot
        # produce a different answer.
        "barUnchanged": bar_unchanged,
    }


@router.post("/evaluate")
async def evaluate_now(symbol: str) -> dict:
    """Evaluate one instrument immediately and store the result."""
    settings = get_settings()
    if not settings.has_supabase:
        raise HTTPException(503, "Supabase is not configured; nothing can be stored.")

    symbol = symbol.upper()
    now = datetime.now(timezone.utc)

    if symbol in OTC_SYMBOLS:
        if not settings.deriv_app_id:
            raise HTTPException(503, "DERIV_APP_ID is not set; the broker feed is unavailable.")
        from app.market_data.deriv_feed import DerivSyntheticFeed
        from app.otc.collector import collect_symbol

        try:
            await collect_symbol(symbol, DerivSyntheticFeed(settings.deriv_app_id), now)
        except Exception as exc:  # noqa: BLE001
            logger.exception("on-demand evaluation failed for %s", symbol)
            raise HTTPException(502, f"Evaluation failed: {exc}") from exc
    else:
        from app.collector.scheduler import build_provider
        from app.otc.market_collector import collect_market_symbol

        try:
            await collect_market_symbol(symbol, build_provider(), now)
        except Exception as exc:  # noqa: BLE001
            logger.exception("on-demand evaluation failed for %s", symbol)
            raise HTTPException(502, f"Evaluation failed: {exc}") from exc

    # Read back what was just written rather than returning the in-memory
    # object: if storage rejected the row, the caller must learn that here
    # and not from a confident response describing a decision that was
    # never persisted.
    from app.storage.candle_repository import asset_id_for_symbol
    from app.storage.supabase_client import get_service_client

    try:
        client = get_service_client()
        rows = (
            client.table("signals")
            .select("direction, status, call_score, put_score, technical_score, market_regime, "
                    "entry_price, expiry_seconds, expiry_at, reasons, warnings, "
                    "generated_at, timeframes_snapshot")
            .eq("asset_id", asset_id_for_symbol(symbol))
            .order("generated_at", desc=True)
            .limit(1)
            .execute()
            .data
        ) or []
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, f"Evaluation ran but could not be read back: {exc}") from exc

    if not rows:
        raise HTTPException(502, "Evaluation ran but no decision was stored.")

    row = rows[0]
    snap = row.get("timeframes_snapshot") or {}
    profile = profile_for(symbol)
    stored_at = datetime.fromisoformat(row["generated_at"])
    # Older than one entry bar means this row is the previous evaluation:
    # the new one was suppressed (cooldown) or storage refused it.
    bar_unchanged = (now - stored_at).total_seconds() > _entry_seconds(profile)

    return {
        "symbol": symbol,
        "direction": row["direction"],
        "status": row["status"],
        "isSignal": row["status"] not in ("REJECTED", "CANDIDATE"),
        "callScore": row.get("call_score"),
        "putScore": row.get("put_score"),
        "score": row.get("technical_score"),
        "regime": row.get("market_regime"),
        "regimeReason": snap.get("regime_reason"),
        "strategy": snap.get("strategy"),
        "feedStatus": snap.get("feed_status"),
        "entryPrice": float(row["entry_price"]) if row.get("entry_price") else None,
        "expirySeconds": row.get("expiry_seconds"),
        "expiryAt": row.get("expiry_at"),
        "reasons": row.get("reasons") or [],
        "warnings": row.get("warnings") or [],
        "rejectionReasons": snap.get("rejection_reasons") or [],
        "evaluatedAt": row["generated_at"],
        "barUnchanged": bar_unchanged,
    }


def _entry_seconds(profile) -> int:
    from app.otc.config import TIMEFRAME_SECONDS

    return TIMEFRAME_SECONDS.get(profile.entry, 60)
