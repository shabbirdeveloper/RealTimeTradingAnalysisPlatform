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

from app.market_data.base import (
    MarketDataError,
    MarketDataProvider,
    RateLimitError,
    TransientMarketDataError,
)
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
    Asset.BTCUSD: "BTC/USD",
    Asset.ETHUSD: "ETH/USD",
}


class TwelveDataProvider(MarketDataProvider):
    name = "twelve_data"

    def __init__(self, api_key: str, *, timeout_seconds: float = 15.0) -> None:
        if not api_key:
            raise ValueError("TwelveDataProvider requires a non-empty api_key")
        self._api_key = api_key
        self._timeout = timeout_seconds

    async def fetch_latest_m5(self, asset: Asset, outputsize: int) -> list[Candle]:
        return await self._fetch_m5(asset, outputsize)

    async def fetch_m5_before(
        self, asset: Asset, end_time: datetime, outputsize: int
    ) -> list[Candle]:
        """One page of M5 history ending at `end_time`, for backfill.

        Separate from fetch_latest_m5 rather than an optional argument on it,
        because the two have different failure semantics: the live poll must
        never silently reach into the past, and a backfill page returning
        nothing means "history ends here", not "the feed is broken".
        """
        return await self._fetch_m5(asset, outputsize, end_time=end_time)

    async def _fetch_m5(
        self, asset: Asset, outputsize: int, *, end_time: datetime | None = None
    ) -> list[Candle]:
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
        if end_time is not None:
            # Twelve Data returns the `outputsize` bars ENDING at this
            # timestamp, so paging backwards means walking this value down.
            params["end_date"] = end_time.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(_BASE_URL, params=params)
        except httpx.HTTPError as exc:
            # Connection refused, DNS failure, timeout -- the request never
            # got an answer, so it is worth one more try.
            raise TransientMarketDataError(
                f"Twelve Data request failed for {symbol}: {exc}"
            ) from exc

        _raise_for_rate_limit(response, symbol)

        try:
            payload = response.json()
        except ValueError as exc:
            # A 5xx often arrives as an HTML error page rather than JSON, so
            # the status code decides retryability here, not the parse failure.
            error_class = (
                TransientMarketDataError if response.status_code >= 500 else MarketDataError
            )
            raise error_class(
                f"Twelve Data returned non-JSON for {symbol}: HTTP {response.status_code}"
            ) from exc

        # Twelve Data reports some errors in the body with HTTP 200, including
        # rate limits, so the payload is checked as well as the status line.
        _raise_for_payload_rate_limit(payload, symbol)

        if response.status_code != 200 or payload.get("status") == "error":
            message = payload.get("message", f"HTTP {response.status_code}")
            if response.status_code >= 500:
                raise TransientMarketDataError(f"Twelve Data error for {symbol}: {message}")
            # 4xx: a bad key, an unknown symbol, a malformed request. The same
            # call will fail identically forever, and each attempt still spends
            # a credit from the daily budget -- so this must NOT be retried.
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


def _retry_after_seconds(response: httpx.Response) -> float | None:
    """Retry-After as delay-seconds. The HTTP-date form is not parsed: it
    would need the server's clock to be trusted, and the caller already
    bounds its own waiting either way."""
    raw = response.headers.get("Retry-After")
    if not raw:
        return None
    try:
        seconds = float(raw.strip())
    except ValueError:
        return None
    return seconds if seconds >= 0 else None


def _raise_for_rate_limit(response: httpx.Response, symbol: str) -> None:
    if response.status_code == 429:
        raise RateLimitError(
            f"Twelve Data rate limit hit for {symbol}",
            retry_after=_retry_after_seconds(response),
        )


# Twelve Data signals an exceeded plan limit with code 429 inside a 200 body.
# Treating that as a generic error would retry it immediately, which is the
# one response guaranteed to make a rate limit worse.
_RATE_LIMIT_CODES = {429}


def _raise_for_payload_rate_limit(payload: dict, symbol: str) -> None:
    if not isinstance(payload, dict):
        return
    if payload.get("code") in _RATE_LIMIT_CODES:
        raise RateLimitError(
            f"Twelve Data rate limit hit for {symbol}: "
            f"{payload.get('message', 'plan limit reached')}"
        )
