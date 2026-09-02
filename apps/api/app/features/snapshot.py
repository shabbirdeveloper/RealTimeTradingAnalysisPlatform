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
from app.features import levels
from app.features import price_action as pa
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
    adx = ind.adx_latest(candles, 14)
    shape = pa.shape_of(candles[-1]) if candles else None
    seq5 = pa.sequence(candles, 5)
    seq10 = pa.sequence(candles, 10)
    zones = levels.find_zones(candles)
    nearest_support = next((z for z in zones if z.kind == "SUPPORT"), None)
    nearest_resistance = next((z for z in zones if z.kind == "RESISTANCE"), None)

    return {
        "price_action": {
            "close": closes[-1] if closes else None,
            "candle_count": len(candles),
            # Normalised by the candle's own range, so these mean the same
            # thing on XAUUSD at 4,300 and EURUSD at 1.16.
            "body_ratio": shape.body_ratio if shape else None,
            "upper_wick_ratio": shape.upper_wick_ratio if shape else None,
            "lower_wick_ratio": shape.lower_wick_ratio if shape else None,
            "close_location": shape.close_location if shape else None,
            "patterns": pa.patterns(candles),
        },
        "sequence": {
            "persistence_5": seq5.directional_persistence if seq5 else None,
            "persistence_10": seq10.directional_persistence if seq10 else None,
            "wick_pressure_5": seq5.wick_pressure if seq5 else None,
            "avg_body_ratio_5": seq5.average_body_ratio if seq5 else None,
            "indecisive_5": seq5.indecisive if seq5 else None,
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
            # Where RSI sits inside its OWN recent range. RSI 58 says little;
            # RSI 58 after ranging 30-70 is a different market from RSI 58
            # that has not left 55-60.
            "stoch_rsi": ind.stoch_rsi_latest(closes, 14, 14),
            "roc_10": ind.rate_of_change(closes, 10),
            # Whether the move is speeding up or running out of energy --
            # not stated directly by RSI or MACD.
            "acceleration_5": ind.momentum_acceleration(closes, 5),
        },
        "trend_strength": {
            # ADX says how strongly price trends WITHOUT saying which way;
            # +DI/-DI carry the direction. Conflating them is how a strong
            # downtrend gets read as a weak uptrend.
            "adx": adx.adx if adx else None,
            "plus_di": adx.plus_di if adx else None,
            "minus_di": adx.minus_di if adx else None,
            "trending": adx.trending if adx else None,
        },
        "levels": {
            "support_price": nearest_support.price if nearest_support else None,
            "support_strength": nearest_support.strength if nearest_support else None,
            "support_distance_atr": nearest_support.distance_atr if nearest_support else None,
            "resistance_price": nearest_resistance.price if nearest_resistance else None,
            "resistance_strength": nearest_resistance.strength if nearest_resistance else None,
            "resistance_distance_atr": nearest_resistance.distance_atr if nearest_resistance else None,
            "zone_count": len(zones),
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
