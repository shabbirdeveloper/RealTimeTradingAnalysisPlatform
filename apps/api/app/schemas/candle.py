"""
Shared types for the market-data pipeline. Mirrors the `assets` and
`candles` tables in supabase/migrations/ -- keep these in sync if the
schema changes.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, ConfigDict


class Asset(str, Enum):
    XAUUSD = "XAUUSD"
    EURUSD = "EURUSD"
    GBPUSD = "GBPUSD"
    # Crypto: the only genuinely 24/7 REAL markets available here, giving
    # honest weekend coverage from a public-market feed.
    BTCUSD = "BTCUSD"
    ETHUSD = "ETHUSD"

    # NOTE: broker-OTC instruments are deliberately ABSENT from this enum.
    # This enum drives the public-market collector loop, and an OTC symbol in
    # it would make the collector fetch Twelve Data's real EUR/USD and store
    # it as EURUSD_OTC -- the precise confusion app/instruments.py exists to
    # prevent. OTC instruments live in the registry (app/instruments.py) and
    # are collected by a separate OTC feed (app/market_data/otc.py).


def is_crypto(asset: Asset) -> bool:
    """Convenience wrapper. The set itself lives in app.instruments so the
    market-hours logic can use it without pulling in pydantic."""
    from app.instruments import is_crypto_symbol

    return is_crypto_symbol(asset.value)


class Timeframe(str, Enum):
    M5 = "M5"
    M15 = "M15"
    H1 = "H1"
    H4 = "H4"


class DataStatus(str, Enum):
    """Matches data_status_type in the DB and the frontend's
    DataStatusPill vocabulary (spec section 42)."""

    LIVE = "LIVE"
    DELAYED = "DELAYED"
    STALE = "STALE"
    OFFLINE = "OFFLINE"


class Candle(BaseModel):
    """One OHLCV bar. `open_time` is the bar's opening timestamp, UTC,
    and must be tz-aware -- naive datetimes are a common source of silent
    off-by-hours bugs in trading systems, so this is enforced, not just
    documented."""

    model_config = ConfigDict(frozen=True)

    open_time: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal | None = None
