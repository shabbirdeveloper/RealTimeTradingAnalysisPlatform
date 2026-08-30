"""
Writes to `audit_logs` (spec section 38 lists audit logging as a security
requirement).

Scope, deliberately: this records *operational and administrative* events
-- who ran a backtest, when a data feed failed, when signals were
resolved. It is NOT a log of every signal the engine produces; those are
already first-class rows in `signals`, including the rejected ones, and
duplicating them here would bury the events an operator actually needs to
notice.

`actor_user_id` is null for anything the system did on its own, which is
most of what this service does -- it runs unattended.

Every write is best-effort: an audit failure must never break the action
being audited. A collector that dies because it couldn't log a warning is
strictly worse than one that keeps collecting with a gap in the log.
"""
from __future__ import annotations

import logging

from app.storage.supabase_client import get_service_client

logger = logging.getLogger(__name__)

# Action names use a `domain.verb` convention so the admin log can be
# filtered by prefix later without parsing free text.
ACTION_BACKTEST_CREATED = "backtest.create"
ACTION_BACKTEST_COMPLETED = "backtest.complete"
ACTION_BACKTEST_FAILED = "backtest.failed"
ACTION_MARKET_DATA_FAILED = "market_data.failed"
ACTION_SIGNALS_RESOLVED = "signals.resolved"
ACTION_SHADOW_RESOLVED = "signals.shadow_resolved"
ACTION_ANALYSIS_FAILED = "analysis.failed"


def record(
    action: str,
    *,
    actor_user_id: str | None = None,
    target_table: str | None = None,
    target_id: str | None = None,
    metadata: dict | None = None,
) -> None:
    """Appends one audit entry. Never raises -- see the module docstring."""
    try:
        get_service_client().table("audit_logs").insert(
            {
                "actor_user_id": actor_user_id,
                "action": action,
                "target_table": target_table,
                "target_id": target_id,
                "metadata": metadata or {},
            }
        ).execute()
    except Exception:  # noqa: BLE001 -- auditing must not break the audited action
        logger.warning("could not write audit log for %s", action, exc_info=True)
