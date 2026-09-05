"""
The centralized feature engine (spec Phase 14).

Strategies CONSUME features; they never compute their own. The previous
engine let each scoring branch reach for its own indicator call, which
meant the same EMA was computed with two different lookbacks in two
places and neither was wrong on its own terms. One computation per bar,
one set of numbers, shared by everything downstream.

The indicator mathematics itself is imported from app.features.* rather
than rewritten. That code is pure -- candles in, numbers out -- with 441
tests behind it and no knowledge of expiries, brokers or instruments.
Retyping it would add risk and remove nothing.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.features.indicators import (
    atr_latest,
    atr_percentile,
    bollinger_latest,
    ema_latest,
    ema_slope,
    macd_latest,
    rate_of_change,
    rsi_latest,
    rsi_slope,
)
from app.features.levels import Zone, find_zones
from app.features.price_action import CandleShape, SequenceReading, patterns, sequence, shape_of
from app.features.structure import StructureReading, classify_structure
from app.otc.config import TIMEFRAMES


@dataclass(frozen=True)
class TimeframeFeatures:
    """Everything known about one timeframe at one instant.

    Every field is Optional because a warming-up series genuinely has no
    RSI yet, and `None` is the honest representation of that. Substituting
    a neutral 50 would let a strategy score a market it cannot actually
    read -- the failure this project has hit five separate times, where a
    catch-all default became a confident statement about the world.
    """

    timeframe: str
    candles: list[dict]
    closes: list[float]
    price: float | None

    ema9: float | None
    ema21: float | None
    ema50: float | None
    ema9_slope: float | None
    ema21_slope: float | None

    rsi: float | None
    rsi_direction: str | None
    macd_hist: float | None
    macd_hist_change: float | None
    roc: float | None

    atr: float | None
    atr_pct: float | None
    bb_width: float | None

    shape: CandleShape | None
    patterns: list[str]
    sequence: SequenceReading | None
    structure: StructureReading
    zones: list[Zone]

    @property
    def ready(self) -> bool:
        """Enough of the series has converged to reason about it."""
        return self.ema21 is not None and self.rsi is not None and self.atr is not None

    @property
    def ema_separation(self) -> float | None:
        """EMA9 minus EMA21 as a fraction of ATR -- scale-free, so the same
        threshold means the same thing on an index priced at 500 and a pair
        priced at 1.15."""
        if self.ema9 is None or self.ema21 is None or not self.atr:
            return None
        return (self.ema9 - self.ema21) / self.atr

    @property
    def price_vs_ema21(self) -> float | None:
        if self.price is None or self.ema21 is None or not self.atr:
            return None
        return (self.price - self.ema21) / self.atr

    @property
    def price_vs_ema50(self) -> float | None:
        if self.price is None or self.ema50 is None or not self.atr:
            return None
        return (self.price - self.ema50) / self.atr


def build_timeframe(timeframe: str, candles: list[dict]) -> TimeframeFeatures:
    """Compute every feature for one timeframe from CLOSED candles only.

    The caller is responsible for having excluded the forming bar. This
    function cannot check that for itself -- a candle carries no flag
    saying whether it is finished -- which is why app.market_data.
    closed_bars exists and why every path into here goes through it.
    """
    closes = [float(c["close"]) for c in candles]
    macd = macd_latest(closes) if len(closes) >= 35 else None
    # MacdResult carries the previous histogram, not the delta. The delta is
    # what the strategies actually ask about ("is momentum building or
    # fading?"), so it is derived once here rather than in each of them.
    hist_change = (
        macd.histogram - macd.histogram_prev
        if macd is not None and macd.histogram_prev is not None
        else None
    )
    bands = bollinger_latest(closes) if len(closes) >= 20 else None

    return TimeframeFeatures(
        timeframe=timeframe,
        candles=candles,
        closes=closes,
        price=closes[-1] if closes else None,
        ema9=ema_latest(closes, 9),
        ema21=ema_latest(closes, 21),
        ema50=ema_latest(closes, 50),
        ema9_slope=ema_slope(closes, 9),
        ema21_slope=ema_slope(closes, 21),
        rsi=rsi_latest(closes),
        rsi_direction=rsi_slope(closes),
        macd_hist=macd.histogram if macd else None,
        macd_hist_change=hist_change,
        roc=rate_of_change(closes),
        atr=atr_latest(candles),
        atr_pct=atr_percentile(candles),
        bb_width=bands.width_pct if bands else None,
        shape=shape_of(candles[-1]) if candles else None,
        patterns=patterns(candles),
        sequence=sequence(candles),
        structure=classify_structure(candles),
        zones=find_zones(candles),
    )


@dataclass(frozen=True)
class MarketContext:
    """One evaluation's complete view of the market. Passed to every
    strategy; strategies must not reach outside it."""

    symbol: str
    now: datetime
    price: float
    frames: dict[str, TimeframeFeatures]
    regime: str

    def frame(self, timeframe: str) -> TimeframeFeatures | None:
        return self.frames.get(timeframe)

    @property
    def missing_timeframes(self) -> list[str]:
        return [tf for tf in TIMEFRAMES if tf not in self.frames or not self.frames[tf].ready]


def build_context(
    symbol: str,
    now: datetime,
    candles_by_timeframe: dict[str, list[dict]],
    *,
    regime: str = "UNKNOWN",
) -> MarketContext:
    frames = {
        tf: build_timeframe(tf, candles)
        for tf, candles in candles_by_timeframe.items()
        if candles
    }
    entry = frames.get("S30") or frames.get("M1")
    price = entry.price if entry and entry.price is not None else 0.0
    return MarketContext(symbol=symbol, now=now, price=price, frames=frames, regime=regime)
