"""
Builds the feature dict stored into `market_features` for one
asset+timeframe+candle. Reuses the same indicator/structure functions the
signal engine uses, so what's persisted for the dashboard/analyzer to
inspect later is exactly what the signal engine actually saw -- not a
separately-computed "display" version that could drift from the real
decision inputs.

Known gap, documented rather than silently absent: this only computes a
feature snapshot for the LATEST candle on each poll cycle, not a full
backfill across every historical candle. A proper backfill job (computing
market_features for all existing candle history in one pass) is a
reasonable next step once there's meaningful history to backfill -- right
now there mostly isn't.
"""
from __future__ import annotations

from app.features import indicators as ind
from app.features import structure as struct


def compute_feature_dict(candles: list[dict]) -> dict:
    closes = [float(c["close"]) for c in candles]

    ema20 = ind.ema_latest(closes, 20)
    ema50 = ind.ema_latest(closes, 50)
    ema200 = ind.ema_latest(closes, 200)
    rsi = ind.rsi_latest(closes, 14)
    macd = ind.macd_latest(closes)
    atr = ind.atr_latest(candles, 14)
    atr_pct = ind.atr_percentile(candles, 14)
    bollinger = ind.bollinger_latest(closes, 20, 2.0)
    structure_reading = struct.classify_structure(candles)

    return {
        "price_action": {
            "close": closes[-1] if closes else None,
            "candle_count": len(candles),
        },
        "trend": {
            "ema20": ema20,
            "ema50": ema50,
            "ema200": ema200,
            "ema20_slope_pct": ind.ema_slope(closes, 20, lookback=3),
        },
        "momentum": {
            "rsi14": rsi,
            "rsi_slope": ind.rsi_slope(closes, 14),
            "macd": macd.macd if macd else None,
            "macd_signal": macd.signal if macd else None,
            "macd_histogram": macd.histogram if macd else None,
            "macd_histogram_prev": macd.histogram_prev if macd else None,
        },
        "volatility": {
            "atr14": atr,
            "atr_percentile": atr_pct,
            "bollinger_width_pct": bollinger.width_pct if bollinger else None,
        },
        "structure": {
            "sequence": structure_reading.sequence,
            "bos": structure_reading.bos,
            "choch": structure_reading.choch,
            "support": structure_reading.support,
            "resistance": structure_reading.resistance,
        },
    }
