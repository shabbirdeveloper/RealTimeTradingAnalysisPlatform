"""
Feed health (spec Phase 7), and the rule that depends on it (Phase 53).

    IF FEED != HEALTHY -> NO SIGNAL

There is no override, and the absence of one is the point. Every serious
loss this project has recorded came from a value that was computed
correctly on data that should not have been trusted, and every override
that exists eventually gets used.

WHY THIS IS NOT A BOOLEAN
-------------------------
"Healthy" and "unhealthy" collapse four different situations that call for
different responses: the feed is fine; the feed is slow but current; the
feed has stopped moving; the feed is gone. The engine only ever needs to
know whether to proceed, but an operator needs to know which of the four
they are looking at -- and a single boolean is exactly the catch-all that
has misled this project repeatedly.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum

from app.otc.config import CONFIG


class FeedStatus(str, Enum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"   # current, but thinner or slower than expected
    STALE = "STALE"         # connected, not moving
    DISCONNECTED = "DISCONNECTED"

    @property
    def may_signal(self) -> bool:
        return self is FeedStatus.HEALTHY


@dataclass(frozen=True)
class MarketDataHealth:
    symbol: str
    status: FeedStatus
    last_tick_at: datetime | None
    latency_ms: float | None
    ticks_per_minute: float
    duplicate_ticks: int
    rejected_ticks: int
    reason: str

    @property
    def may_signal(self) -> bool:
        return self.status.may_signal


def assess(
    symbol: str,
    *,
    last_tick_at: datetime | None,
    ticks_per_minute: float,
    duplicate_ticks: int = 0,
    rejected_ticks: int = 0,
    latency_ms: float | None = None,
    now: datetime | None = None,
) -> MarketDataHealth:
    """Classify the feed. Ordered most-severe first so a disconnected feed
    is never reported as merely thin."""
    now = now or datetime.now(timezone.utc)

    def build(status: FeedStatus, reason: str) -> MarketDataHealth:
        return MarketDataHealth(
            symbol=symbol, status=status, last_tick_at=last_tick_at,
            latency_ms=latency_ms, ticks_per_minute=ticks_per_minute,
            duplicate_ticks=duplicate_ticks, rejected_ticks=rejected_ticks,
            reason=reason,
        )

    if last_tick_at is None:
        return build(FeedStatus.DISCONNECTED, "no tick has ever arrived")

    age = (now - last_tick_at).total_seconds()
    if age > CONFIG.max_bar_age_seconds:
        return build(FeedStatus.DISCONNECTED, f"last tick {age:.0f}s ago")
    if age > CONFIG.max_tick_age_seconds:
        return build(FeedStatus.STALE, f"last tick {age:.0f}s ago")

    # A feed can be current and still untrustworthy: too few ticks means the
    # sub-minute bars are built from almost nothing, so their highs and lows
    # are noise rather than range.
    if ticks_per_minute < CONFIG.min_ticks_per_minute:
        return build(
            FeedStatus.DEGRADED,
            f"{ticks_per_minute:.1f} ticks/min below the {CONFIG.min_ticks_per_minute} floor",
        )

    if rejected_ticks and rejected_ticks > duplicate_ticks + 5:
        return build(FeedStatus.DEGRADED, f"{rejected_ticks} ticks failed validation")

    return build(FeedStatus.HEALTHY, "ok")
