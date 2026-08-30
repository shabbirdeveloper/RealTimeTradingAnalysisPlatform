"""
Reads and writes the `economic_events` table (spec sections 8/25).

Upserts on the natural key (event_name, currency, event_time) added in
migration 20260830000010, so a provider re-fetching the same window
updates each event in place -- important because `actual` only exists
after the release, and a re-fetch is how it gets filled in.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from app.news.base import ProviderEvent
from app.news.blackout import EconomicEvent
from app.storage.supabase_client import get_service_client

logger = logging.getLogger(__name__)


def upsert_events(events: list[ProviderEvent], *, source: str) -> int:
    if not events:
        return 0
    client = get_service_client()
    rows = [
        {
            "event_name": e.event_name,
            "currency": e.currency,
            "event_time": e.event_time.astimezone(timezone.utc).isoformat(),
            "impact": e.impact,
            "previous": e.previous,
            "forecast": e.forecast,
            "actual": e.actual,
            "source": source,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        for e in events
    ]
    client.table("economic_events").upsert(
        rows, on_conflict="event_name,currency,event_time"
    ).execute()
    return len(rows)


def fetch_events_near(
    now: datetime, *, hours_back: int = 6, hours_ahead: int = 12
) -> list[EconomicEvent]:
    """Events in a window around `now`, for the blackout check.

    Deliberately narrow: the blackout only ever cares about events close
    to the present, and pulling the whole calendar on every poll cycle
    would be wasteful.
    """
    client = get_service_client()
    response = (
        client.table("economic_events")
        .select("event_name, currency, event_time, impact")
        .gte("event_time", (now - timedelta(hours=hours_back)).isoformat())
        .lte("event_time", (now + timedelta(hours=hours_ahead)).isoformat())
        .order("event_time", desc=False)
        .execute()
    )
    return [
        EconomicEvent(
            event_name=row["event_name"],
            currency=row["currency"],
            event_time=datetime.fromisoformat(row["event_time"]).astimezone(timezone.utc),
            impact=row["impact"],
        )
        for row in (response.data or [])
    ]
