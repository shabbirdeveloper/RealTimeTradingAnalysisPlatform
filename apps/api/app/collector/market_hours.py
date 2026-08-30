"""
Per-asset "is this market open" check, used only to decide whether the
collector should bother polling -- NOT the session-detection engine in
spec section 6/7 (Asian/London/NY), which lives in the feature engine.

Two very different schedules now coexist:

  Forex / gold  -- roughly Sunday ~21:00 UTC through Friday ~22:00 UTC.
  Crypto        -- genuinely continuous, including weekends and holidays.

Getting this wrong in either direction is bad: polling a closed forex
market burns API credits for repeated identical candles, while pausing a
crypto asset on a Saturday would blind the platform during a period it
can legitimately trade. So the check takes the asset.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.instruments import is_crypto_symbol


def is_market_open(asset: str | None = None, now: datetime | None = None) -> bool:
    """Whether `asset`'s market is currently open. Accepts a symbol string
    or an `Asset` member (which is a `str` Enum).

    `asset=None` answers for the forex/gold schedule, which is the
    conservative default: callers that don't specify an asset get the
    schedule that actually closes, never a blanket "always open".
    """
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)

    if asset is not None and is_crypto_symbol(asset):
        return True  # crypto never closes

    weekday = now.weekday()  # Monday=0 ... Sunday=6
    if weekday == 5:  # Saturday: always closed
        return False
    if weekday == 6 and now.hour < 21:  # Sunday before ~21:00 UTC: closed
        return False
    if weekday == 4 and now.hour >= 22:  # Friday from ~22:00 UTC: closed
        return False
    return True


def any_market_open(now: datetime | None = None, symbols: list[str] | None = None) -> bool:
    """True if ANY configured asset can be polled right now. Since crypto is
    always open this is effectively always true today, but it keeps the
    scheduler's intent explicit rather than hardcoding that assumption.

    `symbols` defaults to the configured Asset enum, imported lazily so this
    module stays usable without pydantic installed."""
    if symbols is None:
        from app.schemas.candle import Asset

        symbols = [a.value for a in Asset]
    return any(is_market_open(symbol, now) for symbol in symbols)
