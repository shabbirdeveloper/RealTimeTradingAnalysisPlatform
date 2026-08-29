"""
Twelve Data implementation of MarketDataProvider.
Docs: https://twelvedata.com/docs#time-series

Only ever requests interval=5min -- see base.py's docstring for why M15/H1/
H4 are derived in-process instead of fetched separately (keeps API credit
usage to roughly 1/4 of the naive "fetch every timeframe" approach).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

import httpx

from app.market_data.base import MarketDataError, MarketDataProvider
from app.schemas.candle import Asset, Candle

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.twelvedata.com/time_series"

# Twelve Data's own symbol notation (https://twelvedata.com/forex,
# https://twelvedata.com/commodities). Kept local to this file -- a second
# provider gets its own map in its own file, never a shared global one,
# since provider symbol conventions don't line up with each other.
_SYMBOL_MAP: dict[Asset, str] = {
    Asset.XAUUSD: "XAU/USD",
    Asset.EURUSD: "EUR/USD",
    Asset.GBPUSD: "GBP/USD",
}


class TwelveDataProvider(MarketDataProvider):
    name = "twelve_data"

    def __init__(self, api_key: str, *, timeout_seconds: float = 15.0) -> None:
        if not api_key:
            raise ValueError("TwelveDataProvider requires a non-empty api_key")
        self._api_key = api_key
        self._timeout = timeout_seconds

    async def fetch_latest_m5(self, asset: Asset, outputsize: int) -> list[Candle]:
        symbol = _SYMBOL_MAP[asset]
        params = {
            "symbol": symbol,
            "interval": "5min",
            "outputsize": str(outputsize),
            # Force UTC so open_time never depends on the exchange's local
            # timezone -- naive/ambiguous timestamps are exactly the kind
            # of bug that silently corrupts everything downstream.
            "timezone": "UTC",
            "apikey": self._api_key,
        }
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(_BASE_URL, params=params)
        except httpx.HTTPError as exc:
            raise MarketDataError(f"Twelve Data request failed for {symbol}: {exc}") from exc

        try:
            payload = response.json()
        except ValueError as exc:
            raise MarketDataError(
                f"Twelve Data returned non-JSON for {symbol}: HTTP {response.status_code}"
            ) from exc

        if response.status_code != 200 or payload.get("status") == "error":
            message = payload.get("message", f"HTTP {response.status_code}")
            raise MarketDataError(f"Twelve Data error for {symbol}: {message}")

        values = payload.get("values")
        if not values:
            raise MarketDataError(f"Twelve Data returned no candles for {symbol}")

        try:
            candles = [_parse_value(v) for v in values]
        except (KeyError, InvalidOperation, ValueError) as exc:
            raise MarketDataError(
                f"Twelve Data returned an unparseable candle for {symbol}: {exc}"
            ) from exc

        # Twelve Data returns newest-first; the rest of the pipeline
        # (aggregation, storage) expects oldest-first.
        candles.sort(key=lambda c: c.open_time)
        return candles


def _parse_value(value: dict) -> Candle:
    open_time = datetime.strptime(value["datetime"], "%Y-%m-%d %H:%M:%S").replace(
        tzinfo=timezone.utc
    )
    volume_raw = value.get("volume")
    return Candle(
        open_time=open_time,
        open=Decimal(value["open"]),
        high=Decimal(value["high"]),
        low=Decimal(value["low"]),
        close=Decimal(value["close"]),
        volume=Decimal(volume_raw) if volume_raw not in (None, "") else None,
    )
