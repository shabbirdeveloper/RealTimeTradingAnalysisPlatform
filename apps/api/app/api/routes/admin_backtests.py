"""
Admin backtest endpoints (spec section 48):
    POST /admin/backtests        -- queue a run
    GET  /admin/backtests/{id}   -- poll its status/results

Auth: a shared secret in the `X-Admin-Api-Key` header, checked against
ADMIN_API_KEY. This service holds the Supabase service-role key and has
no user auth of its own, so the endpoint FAILS CLOSED -- with no
ADMIN_API_KEY configured it refuses every request rather than running
open. That is a minimum bar and not a substitute for putting real auth in
front of this service before it is exposed publicly.

Runs happen in a FastAPI background task: a replay over a long window can
take a while, and the request shouldn't hold a connection open for it.
The `backtests` row carries PENDING -> RUNNING -> COMPLETED/FAILED so the
caller can poll.
"""
from __future__ import annotations

import logging
from datetime import date

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException
from pydantic import BaseModel, Field, field_validator

from app.backtesting.runner import execute_backtest
from app.config import get_settings
from app.schemas.candle import Asset
from app.storage.candle_repository import _asset_id_map
from app.storage.supabase_client import get_service_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/backtests", tags=["admin"])


def _require_admin(provided_key: str | None) -> None:
    settings = get_settings()
    if not settings.has_admin_api_key:
        raise HTTPException(
            status_code=503,
            detail="ADMIN_API_KEY is not configured on this service; admin endpoints are disabled.",
        )
    if not provided_key or provided_key != settings.admin_api_key:
        raise HTTPException(status_code=401, detail="Invalid or missing X-Admin-Api-Key.")


class BacktestRequest(BaseModel):
    asset: str | None = Field(default=None, description="Asset symbol, or null/omitted for all configured assets")
    start_date: date
    end_date: date
    # Named for what it actually is. Spec section 32 calls this input
    # "minimum confidence", but there is no calibrated model confidence to
    # threshold on yet (Phase 6), so the real knob is the technical score.
    # Calling it "confidence" here would imply a model that doesn't exist.
    min_technical_score: int = Field(default=78, ge=0, le=99)
    expiry_minutes: int | None = Field(default=None)
    session: str | None = Field(default=None)
    regime: str | None = Field(default=None)
    step_minutes: int = Field(default=5, ge=5, le=240)

    @field_validator("expiry_minutes")
    @classmethod
    def _valid_expiry(cls, v: int | None) -> int | None:
        if v is not None and v not in (15, 30, 60):
            raise ValueError("expiry_minutes must be 15, 30 or 60")
        return v

    @field_validator("end_date")
    @classmethod
    def _end_not_in_future(cls, v: date) -> date:
        if v > date.today():
            raise ValueError("end_date cannot be in the future")
        return v


@router.post("")
def create_backtest(
    request: BacktestRequest,
    background_tasks: BackgroundTasks,
    x_admin_api_key: str | None = Header(default=None),
) -> dict:
    _require_admin(x_admin_api_key)

    if request.start_date > request.end_date:
        raise HTTPException(status_code=422, detail="start_date must be on or before end_date")

    if request.asset:
        try:
            assets = [Asset(request.asset)]
        except ValueError:
            raise HTTPException(status_code=422, detail=f"Unknown asset {request.asset!r}") from None
    else:
        assets = list(Asset)

    client = get_service_client()
    row = {
        "asset_id": _asset_id_map()[assets[0]] if request.asset else None,
        "expiry_minutes": request.expiry_minutes,
        "start_date": request.start_date.isoformat(),
        "end_date": request.end_date.isoformat(),
        "min_confidence": request.min_technical_score,
        "session_filter": request.session,
        "regime_filter": request.regime,
        "status": "PENDING",
    }
    response = client.table("backtests").insert(row).execute()
    rows = response.data or []
    if not rows:
        raise HTTPException(status_code=500, detail="Could not create the backtest row")
    backtest_id = rows[0]["id"]

    background_tasks.add_task(
        execute_backtest,
        backtest_id,
        assets=assets,
        start_date=request.start_date.isoformat(),
        end_date=request.end_date.isoformat(),
        technical_score_threshold=request.min_technical_score,
        expiry_filter=request.expiry_minutes,
        session_filter=request.session,
        regime_filter=request.regime,
        step_minutes=request.step_minutes,
    )

    return {"id": backtest_id, "status": "PENDING"}


@router.get("/{backtest_id}")
def get_backtest(backtest_id: str, x_admin_api_key: str | None = Header(default=None)) -> dict:
    _require_admin(x_admin_api_key)

    response = (
        get_service_client().table("backtests").select("*").eq("id", backtest_id).limit(1).execute()
    )
    rows = response.data or []
    if not rows:
        raise HTTPException(status_code=404, detail="Backtest not found")
    return rows[0]
