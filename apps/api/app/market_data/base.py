"""
Provider abstraction. Every concrete provider (Twelve Data today, anything
else later) implements fetch_latest_m5() and nothing else -- M15/H1/H4 are
always derived in-process by app/aggregation.py, never fetched directly.
This keeps the provider interface tiny and keeps API credit usage
independent of how many timeframes the app analyzes.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.schemas.candle import Asset, Candle


class MarketDataError(Exception):
    """Raised when a provider fails to return usable data -- a bad API
    key, a rate limit, a network error, or a malformed response. Callers
    must NEVER catch this and substitute fake/estimated candles; the
    correct response to a MarketDataError is to skip that poll cycle,
    record the failure (system_health), and let the staleness/DataStatus
    logic reflect reality (spec section 42/50: never show stale data as
    live, never fabricate data)."""


class MarketDataProvider(ABC):
    name: str

    @abstractmethod
    async def fetch_latest_m5(self, asset: Asset, outputsize: int) -> list[Candle]:
        """Return the most recent `outputsize` M5 candles for `asset`,
        oldest first. Raises MarketDataError on any failure -- never
        returns a partial/best-effort result silently."""
        raise NotImplementedError
