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
