"""
Loads candle history for a backtest and persists its results into the
existing `backtests` / `backtest_signals` tables (spec sections 13/32).

`backtests` rows move PENDING -> RUNNING -> COMPLETED/FAILED, so a long
replay is observable while it runs rather than appearing to hang, and a
crash leaves a FAILED row with its error rather than a stuck PENDING one.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from app.backtesting.engine import BacktestSummary
from app.schemas.candle import Asset, Timeframe
from app.storage.candle_repository import _asset_id_map
from app.storage.supabase_client import get_service_client

logger = logging.getLogger(__name__)

# Extra history pulled in before the window so indicators are already
# warmed up at the first decision point -- without it, the start of every
# backtest would be dominated by "insufficient data" NO_TRADEs. 300 H4
# bars is ~50 days; the same span covers every faster timeframe.
_WARMUP = timedelta(days=55)


def load_history(asset: Asset, start: datetime, end: datetime) -> dict[str, list[dict]]:
    """Candles for one asset across all four timeframes, oldest-first.

    Deliberately fetches past `end` too: those bars resolve the outcomes of
    signals generated near the end of the window. They can never leak into
    a decision -- every decision goes through `replay.slice_history`.
    """
    client = get_service_client()
    asset_id = _asset_id_map()[asset]
    history: dict[str, list[dict]] = {}

    for timeframe in (Timeframe.M5, Timeframe.M15, Timeframe.H1, Timeframe.H4):
        response = (
            client.table("candles")
            .select("open_time, open, high, low, close")
            .eq("asset_id", asset_id)
            .eq("timeframe", timeframe.value)
            .gte("open_time", (start - _WARMUP).isoformat())
            .lte("open_time", (end + timedelta(hours=2)).isoformat())
            .order("open_time", desc=False)
            .limit(20000)
            .execute()
        )
        history[timeframe.value] = [
            {
                "open_time": datetime.fromisoformat(row["open_time"]).astimezone(timezone.utc),
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
            }
            for row in (response.data or [])
        ]

    return history


def mark_running(backtest_id: str) -> None:
    get_service_client().table("backtests").update({
        "status": "RUNNING",
        "started_at": datetime.now(timezone.utc).isoformat(),
    }).eq("id", backtest_id).execute()


def mark_failed(backtest_id: str, message: str) -> None:
    get_service_client().table("backtests").update({
        "status": "FAILED",
        "error_message": message[:2000],
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }).eq("id", backtest_id).execute()


def save_results(backtest_id: str, summary: BacktestSummary) -> None:
    client = get_service_client()

    client.table("backtests").update({
        "status": "COMPLETED",
        "total_opportunities": summary.total_opportunities,
        "accepted_signals": summary.accepted_signals,
        "rejected_signals": summary.rejected_signals,
        "wins": summary.wins,
        "losses": summary.losses,
        "draws": summary.draws,
        "win_rate": summary.win_rate,
        "accuracy": summary.accuracy,
        "signal_coverage": summary.signal_coverage,
        "max_win_streak": summary.max_win_streak,
        "max_loss_streak": summary.max_loss_streak,
        "performance_by_pair": summary.performance_by_pair,
        "performance_by_expiry": summary.performance_by_expiry,
        "performance_by_session": summary.performance_by_session,
        "performance_by_regime": summary.performance_by_regime,
        "performance_by_confidence_bucket": summary.performance_by_confidence_bucket,
        # Caveats (unresolved signals, empty windows) ride along in
        # error_message even on success -- the UI surfaces them so a
        # thin-history result is never read as a clean one.
        "error_message": " ".join(summary.notes)[:2000] if summary.notes else None,
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }).eq("id", backtest_id).execute()

    asset_ids = {asset.value: asset_id for asset, asset_id in _asset_id_map().items()}
    rows = [
        {
            "backtest_id": backtest_id,
            "asset_id": asset_ids[o.asset],
            "direction": o.direction,
            "generated_at": o.generated_at.isoformat(),
            "entry_price": str(o.entry_price) if o.entry_price is not None else None,
            "expiry_minutes": o.expiry_minutes,
            "technical_score": o.technical_score,
            "calibrated_confidence": None,  # Phase 6 (ML) not built -- never fabricated
            "grade": o.grade,
            "market_regime": o.market_regime,
            "session": o.session,
            "accepted": o.accepted,
            "result": o.result,
            "closing_price": str(o.closing_price) if o.closing_price is not None else None,
        }
        for o in summary.opportunities
    ]

    # Chunked: a long replay can produce thousands of rows, and one
    # oversized insert is the easy way to hit a request-size limit.
    for i in range(0, len(rows), 500):
        client.table("backtest_signals").insert(rows[i:i + 500]).execute()
