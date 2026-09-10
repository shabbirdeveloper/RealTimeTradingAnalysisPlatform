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
    a plain upsert, so this is a send-count, not a diff-count).

    `Asset` is the public-market enum, so every bar reaching here is real
    market data and is labelled PUBLIC_MARKET. It used to write no
    feed_kind at all, leaving genuine market bars indistinguishable from
    unlabelled rows of unknown origin.
    """
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
            "feed_kind": "PUBLIC_MARKET",
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

def fetch_first_candle_at_or_after(
    asset: Asset, timeframe: Timeframe, at
) -> tuple[Candle, str] | None:
    """Real closing price lookup for signal resolution (spec section 49):
    the earliest stored candle at/after `at`, plus the real provider
    `source` string it was written with (spec: "store the exact quote
    source used"). Returns None if no candle has been stored yet at/after
    that time -- resolution should simply wait for the next poll cycle
    rather than guess."""
    asset_id = _asset_id_map()[asset]
    client = get_service_client()
    response = (
        client.table("candles")
        .select("open_time, open, high, low, close, volume, source")
        .eq("asset_id", asset_id)
        .eq("timeframe", timeframe.value)
        .gte("open_time", at.astimezone(timezone.utc).isoformat())
        .order("open_time", desc=False)
        .limit(1)
        .execute()
    )
    rows = response.data or []
    if not rows:
        return None
    row = rows[0]
    candle = Candle(
        open_time=datetime.fromisoformat(row["open_time"]).astimezone(timezone.utc),
        open=Decimal(str(row["open"])),
        high=Decimal(str(row["high"])),
        low=Decimal(str(row["low"])),
        close=Decimal(str(row["close"])),
        volume=Decimal(str(row["volume"])) if row["volume"] is not None else None,
    )
    return candle, row["source"]



# ---------------------------------------------------------------------------
# Broker-OTC storage
#
# Keyed by SYMBOL rather than by the Asset enum, on purpose. That enum drives
# the public-market collector loop, and OTC symbols are deliberately absent
# from it so a broker instrument can never be swept into a cycle that would
# price it from a public feed. Reusing it here would undo that.
# ---------------------------------------------------------------------------


@lru_cache
def asset_id_for_symbol(symbol: str) -> str:
    client = get_service_client()
    rows = (
        client.table("assets").select("id, symbol").eq("symbol", symbol).limit(1).execute().data
    ) or []
    if not rows:
        raise RuntimeError(
            f"assets table has no row for {symbol!r}. Broker-OTC instruments are "
            "seeded by migration; run it before collecting them."
        )
    return rows[0]["id"]


def upsert_otc_candles(
    symbol: str,
    timeframe: str,
    bars: list[dict],
    *,
    source: str,
    feed_kind: str = "BROKER_OTC",
) -> int:
    """Stores closed bars.

    `feed_kind` is written on every row. It is what lets a later reader prove
    a bar came from the broker's own generator rather than from a public
    market -- the check that stops a real EUR/USD candle ever being scored
    against a broker instrument of a similar name.

    It therefore has to be told the truth. The default suits the broker feed,
    which is what this was written for; the public-market collector passes
    PUBLIC_MARKET. Letting a Twelve Data bar default into BROKER_OTC would
    write a lie into the one column whose whole purpose is provenance, and
    the lie would be invisible afterwards -- the row would look exactly like
    a broker bar.
    """
    if not bars:
        return 0

    asset_id = asset_id_for_symbol(symbol)
    rows = [
        {
            "asset_id": asset_id,
            "timeframe": timeframe,
            "open_time": bar["open_time"].astimezone(timezone.utc).isoformat(),
            "open": str(bar["open"]),
            "high": str(bar["high"]),
            "low": str(bar["low"]),
            "close": str(bar["close"]),
            "volume": None,
            "source": source,
            "feed_kind": feed_kind,
        }
        for bar in bars
    ]
    get_service_client().table("candles").upsert(
        rows, on_conflict="asset_id,timeframe,open_time"
    ).execute()
    return len(rows)


def fetch_recent_otc_candles(symbol: str, timeframe: str, limit: int) -> list[dict]:
    """Most recent stored OTC bars, oldest-first, as plain dicts — the shape
    the feature engine and replay slicer already take."""
    asset_id = asset_id_for_symbol(symbol)
    rows = (
        get_service_client().table("candles")
        .select("open_time, open, high, low, close")
        .eq("asset_id", asset_id)
        .eq("timeframe", timeframe)
        .order("open_time", desc=True)
        .limit(limit)
        .execute()
        .data
    ) or []
    out = [
        {
            "open_time": datetime.fromisoformat(r["open_time"].replace("Z", "+00:00")),
            "open": float(r["open"]),
            "high": float(r["high"]),
            "low": float(r["low"]),
            "close": float(r["close"]),
        }
        for r in rows
    ]
    out.reverse()  # oldest-first, which everything downstream assumes
    return out
