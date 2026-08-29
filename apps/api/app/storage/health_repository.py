"""
Writes to the `system_health` table (spec section 29/35: admin system
status; section 34: market-data monitoring). One row per component,
keyed by component name and UPSERTED -- the admin dashboard should always
read current state, not a growing history of every check ever made.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from app.storage.supabase_client import get_service_client

ComponentStatus = Literal["Healthy", "Warning", "Offline"]


def report_component_health(component: str, *, status: ComponentStatus, details: dict) -> None:
    client = get_service_client()
    client.table("system_health").upsert(
        {
            "component": component,
            "status": status,
            "details": details,
            "last_checked_at": datetime.now(timezone.utc).isoformat(),
        },
        on_conflict="component",
    ).execute()
