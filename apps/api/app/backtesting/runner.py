"""
Orchestrates a single backtest run: load history -> replay -> persist.
Separated from the API layer so it can also be driven from a script or a
future queue worker without going through HTTP.
"""
from __future__ import annotations

import logging
from datetime import datetime, time, timezone

from app.backtesting.engine import run_backtest
from app.backtesting.repository import load_history, mark_failed, mark_running, save_results
from app.schemas.candle import Asset
from app.storage import audit_repository as audit

logger = logging.getLogger(__name__)


def execute_backtest(
    backtest_id: str,
    *,
    assets: list[Asset],
    start_date: str,
    end_date: str,
    technical_score_threshold: int,
    expiry_filter: int | None = None,
    session_filter: str | None = None,
    regime_filter: str | None = None,
    step_minutes: int = 5,
) -> None:
    """Runs to completion, recording status on the `backtests` row as it
    goes. Never raises -- a failure is recorded as FAILED with its message
    so the admin UI can show what went wrong instead of a row stuck in
    PENDING forever."""
    try:
        mark_running(backtest_id)

        start = datetime.combine(datetime.fromisoformat(start_date).date(), time.min, tzinfo=timezone.utc)
        end = datetime.combine(datetime.fromisoformat(end_date).date(), time.max, tzinfo=timezone.utc)

        candles_by_asset = {asset.value: load_history(asset, start, end) for asset in assets}

        summary = run_backtest(
            candles_by_asset,
            start=start,
            end=end,
            technical_score_threshold=technical_score_threshold,
            expiry_filter=expiry_filter,
            session_filter=session_filter,
            regime_filter=regime_filter,
            step_minutes=step_minutes,
        )

        save_results(backtest_id, summary)
        logger.info(
            "backtest %s completed: %d opportunities, %d accepted, %d/%d W/L",
            backtest_id, summary.total_opportunities, summary.accepted_signals,
            summary.wins, summary.losses,
        )
        audit.record(
            audit.ACTION_BACKTEST_COMPLETED,
            target_table="backtests",
            target_id=backtest_id,
            metadata={
                "opportunities": summary.total_opportunities,
                "accepted": summary.accepted_signals,
                "wins": summary.wins,
                "losses": summary.losses,
                "win_rate": summary.win_rate,
            },
        )
    except Exception as exc:  # noqa: BLE001 -- must always land as a FAILED row
        logger.exception("backtest %s failed", backtest_id)
        audit.record(
            audit.ACTION_BACKTEST_FAILED,
            target_table="backtests",
            target_id=backtest_id,
            metadata={"error": str(exc)},
        )
        try:
            mark_failed(backtest_id, str(exc))
        except Exception:  # noqa: BLE001
            logger.exception("could not even record failure for backtest %s", backtest_id)
