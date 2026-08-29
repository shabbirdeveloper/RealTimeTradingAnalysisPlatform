"""
Deterministic, seeded, zero-network mock provider. Exists to exercise the
rest of the pipeline (aggregation, storage, health reporting) locally
without an API key or spending real credits -- NOT for production use.

The prices generated here are arbitrary round placeholders, not real
market levels. Anything that displays them must be clearly labeled DEMO
DATA (spec section 50) -- this provider does not label its own output,
that's the caller's responsibility, same as the frontend's demo engine.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.market_data.base import MarketDataProvider
from app.schemas.candle import Asset, Candle

# Arbitrary placeholder base prices -- NOT real quotes.
_BASE_PRICE: dict[Asset, Decimal] = {
    Asset.XAUUSD: Decimal("2000.00"),
    Asset.EURUSD: Decimal("1.1000"),
    Asset.GBPUSD: Decimal("1.3000"),
}

# Roughly asset-appropriate per-candle volatility, purely for making the
# demo data look plausible -- not calibrated to real market behavior.
_STEP_PCT: dict[Asset, Decimal] = {
    Asset.XAUUSD: Decimal("0.0006"),
    Asset.EURUSD: Decimal("0.0004"),
    Asset.GBPUSD: Decimal("0.0005"),
}


class DemoMarketDataProvider(MarketDataProvider):
    name = "demo"

    async def fetch_latest_m5(self, asset: Asset, outputsize: int) -> list[Candle]:
        rng = random.Random(f"{asset.value}-{_current_m5_bucket().isoformat()}")
        price = _BASE_PRICE[asset]
        step = price * _STEP_PCT[asset]

        end = _current_m5_bucket()
        candles: list[Candle] = []
        for i in range(outputsize, 0, -1):
            open_time = end - timedelta(minutes=5 * i)
            drift = Decimal(rng.uniform(-1, 1)) * step
            open_price = price
            close_price = max(price + drift, step)  # keep it positive
            high = max(open_price, close_price) + abs(Decimal(rng.uniform(0, 1)) * step)
            low = min(open_price, close_price) - abs(Decimal(rng.uniform(0, 1)) * step)
            candles.append(
                Candle(
                    open_time=open_time,
                    open=_quantize(open_price, asset),
                    high=_quantize(high, asset),
                    low=_quantize(low, asset),
                    close=_quantize(close_price, asset),
                    volume=None,
                )
            )
            price = close_price

        return candles


def _current_m5_bucket() -> datetime:
    now = datetime.now(timezone.utc)
    floored_minute = (now.minute // 5) * 5
    return now.replace(minute=floored_minute, second=0, microsecond=0)


def _quantize(value: Decimal, asset: Asset) -> Decimal:
    places = Decimal("0.01") if asset == Asset.XAUUSD else Decimal("0.00001")
    return value.quantize(places)
