"""
Writes computed technical features into `market_features` (spec section
6/36). One row per asset+timeframe+candle_time+feature_version, upserted
so re-running a poll cycle over the same latest candle never duplicates.
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.schemas.candle import Asset, Timeframe
from app.storage.candle_repository import _asset_id_map
from app.storage.supabase_client import get_service_client

FEATURE_VERSION = "rule-based-v1"  # bump when the feature/indicator logic changes meaningfully


def upsert_features(
    asset: Asset, timeframe: Timeframe, candle_time: datetime, features: dict
) -> None:
    asset_id = _asset_id_map()[asset]
    client = get_service_client()
    row = {
        "asset_id": asset_id,
        "timeframe": timeframe.value,
        "candle_time": candle_time.astimezone(timezone.utc).isoformat(),
        "feature_version": FEATURE_VERSION,
        "features": features,
    }
    client.table("market_features").upsert(
        row, on_conflict="asset_id,timeframe,candle_time,feature_version"
    ).execute()
