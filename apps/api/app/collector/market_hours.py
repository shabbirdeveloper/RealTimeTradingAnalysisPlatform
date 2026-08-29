"""
Coarse "is the forex/gold market open" check, used only to decide whether
the collector should bother polling -- NOT the session-detection engine
described in spec section 6/7 (Asian/London/NY sessions), which belongs to
the feature engine in a later phase. Deliberately conservative and simple:
skip polling on the weekend, poll otherwise.
"""

from __future__ import annotations

from datetime import datetime, timezone


def is_market_open(now: datetime | None = None) -> bool:
    """Forex/gold trade roughly continuously from Sunday ~22:00 UTC
    through Friday ~22:00 UTC. This errs on the side of polling a bit
    more than strictly necessary near the boundaries, rather than risking
    a missed candle right at the open."""
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    weekday = now.weekday()  # Monday=0 ... Sunday=6

    if weekday == 5:  # Saturday: always closed
        return False
    if weekday == 6 and now.hour < 21:  # Sunday before ~21:00 UTC: closed
        return False
    if weekday == 4 and now.hour >= 22:  # Friday from ~22:00 UTC: closed
        return False
    return True
