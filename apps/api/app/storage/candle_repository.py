"""
Writes and reads candles in the `candles` table. Upserts are keyed on the
same (asset_id, timeframe, open_time) unique constraint the migration
defines, so re-running the collector over already-stored candles is
always safe -- no duplicate rows, no need for the caller to track what
was already saved.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from functools import lru_cache

from app.schemas.candle import Asset, Candle, Timeframe
from app.storage.supabase_client import get_service_client


@lru_cache
def _asset_id_map() -> dict[Asset, str]:
    """Looks up each configured asset's UUID from the `assets` table,
    keyed by the `symbol` column ('XAUUSD', 'EURUSD', 'GBPUSD'). Cached
    for the process lifetime -- these are seed rows, not expected to
    change while the collector is running. Call _asset_id_map.cache_clear()
    in tests if that ever matters."""
    client = get_service_client()
    response = (
        client.table("assets")
        .select("id, symbol")
        .in_("symbol", [a.value for a in Asset])
        .execute()
    )
    rows = response.data or []
    by_symbol = {row["symbol"]: row["id"] for row in rows}
    missing = [a.value for a in Asset if a.value not in by_symbol]
    if missing:
        raise RuntimeError(
            f"assets table is missing rows for: {missing}. Run the "
            "migrations' seed data before starting the collector."
        )
    return {Asset(symbol): asset_id for symbol, asset_id in by_symbol.items()}


def upsert_candles(
    asset: Asset, timeframe: Timeframe, candles: list[Candle], *, source: str
) -> int:
    """Upserts `candles` for one asset+timeframe. Returns the number of
    rows sent (Postgres doesn't report how many actually changed through
    a plain upsert, so this is a send-count, not a diff-count)."""
    if not candles:
        return 0

    asset_id = _asset_id_map()[asset]
    client = get_service_client()

    rows = [
        {
            "asset_id": asset_id,
            "timeframe": timeframe.value,
            "open_time": candle.open_time.astimezone(timezone.utc).isoformat(),
            "open": str(candle.open),
            "high": str(candle.high),
            "low": str(candle.low),
            "close": str(candle.close),
            "volume": str(candle.volume) if candle.volume is not None else None,
            "source": source,
        }
        for candle in candles
    ]

    client.table("candles").upsert(rows, on_conflict="asset_id,timeframe,open_time").execute()
    return len(rows)


def fetch_recent_candles(asset: Asset, timeframe: Timeframe, limit: int) -> list[Candle]:
    """Reads the most recent `limit` stored candles for asset+timeframe,
    returned oldest-first -- used to give aggregation more history than a
    single provider fetch just returned (e.g. right after a restart, or
    when deriving H4 bars which need 48 M5 bars each)."""
    asset_id = _asset_id_map()[asset]
    client = get_service_client()
    response = (
        client.table("candles")
        .select("open_time, open, high, low, close, volume")
        .eq("asset_id", asset_id)
        .eq("timeframe", timeframe.value)
        .order("open_time", desc=True)
        .limit(limit)
        .execute()
    )
    rows = response.data or []
    candles = [
        Candle(
            open_time=datetime.fromisoformat(row["open_time"]).astimezone(timezone.utc),
            open=Decimal(str(row["open"])),
            high=Decimal(str(row["high"])),
            low=Decimal(str(row["low"])),
            close=Decimal(str(row["close"])),
            volume=Decimal(str(row["volume"])) if row["volume"] is not None else None,
        )
        for row in rows
    ]
    candles.reverse()  # rows came back newest-first
    return candles
