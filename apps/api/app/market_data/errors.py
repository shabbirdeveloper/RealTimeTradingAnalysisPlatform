"""
Provider error hierarchy.

Separate from base.py so it depends on nothing -- not the candle schema,
not pydantic. The retry layer needs to tell these apart, and a retry
policy that cannot be unit-tested without a network stack and a settings
file is a retry policy nobody verifies.

Imported through base.py as well, so existing `from app.market_data.base
import MarketDataError` callers keep working.
"""
from __future__ import annotations


class MarketDataError(Exception):
    """Raised when a provider fails to return usable data -- a bad API
    key, a rate limit, a network error, or a malformed response. Callers
    must NEVER catch this and substitute fake/estimated candles; the
    correct response to a MarketDataError is to skip that poll cycle,
    record the failure (system_health), and let the staleness/DataStatus
    logic reflect reality (spec section 42/50: never show stale data as
    live, never fabricate data)."""


class TransientMarketDataError(MarketDataError):
    """A failure that a later identical request could plausibly survive: a
    network blip, a timeout, a provider 5xx.

    Split out from MarketDataError because retrying the OTHER kind is
    actively harmful. A bad API key or an unknown symbol returns the same
    error every time, and on a metered provider each pointless retry spends
    a credit from the same daily budget the collector needs to stay live.
    Retrying a permanent failure is how a small misconfiguration becomes an
    outage."""


class RateLimitError(TransientMarketDataError):
    """The provider said to slow down (HTTP 429, or its own error code).

    Carries `retry_after` in seconds when the provider supplied one. It is
    advisory, not a promise: callers must still bound how long they are
    willing to wait, because a provider asking for a 60-second pause during
    a 600-second poll cycle is fine, and one asking for an hour is not
    something to block the scheduler on."""

    def __init__(self, message: str, *, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after
