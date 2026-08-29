"""
Market regime classification (spec section 7): TRENDING_UP, TRENDING_DOWN,
RANGING, HIGH_VOLATILITY, LOW_VOLATILITY, or UNSTABLE, derived from real
H1 indicators/structure.

NEWS_MODE is part of the enum but is never returned by this module --
classifying it correctly requires the economic calendar integration
(spec section 8 / Phase 7), which hasn't been built yet. Returning
NEWS_MODE without real calendar data would be exactly the kind of fake
signal this project must not produce, so regime classification here is
honestly silent on news until that phase lands (see
`docs/PHASE-STATUS.md`). Downstream, the signal engine adds its own
explicit warning that the news filter isn't active yet.
"""
from __future__ import annotations

from app.features import indicators as ind
from app.features.structure import StructureReading


def classify_regime(h1_candles: list[dict], h1_structure: StructureReading) -> tuple[str, str]:
    """Returns (regime, reason)."""
    closes = [float(c["close"]) for c in h1_candles]

    atr_pct = ind.atr_percentile(h1_candles, period=14)
    ema20 = ind.ema_latest(closes, 20)
    ema50 = ind.ema_latest(closes, 50)
    ema_slope20 = ind.ema_slope(closes, 20, lookback=5)

    if atr_pct is None or ema20 is None or ema50 is None or ema_slope20 is None:
        return "UNSTABLE", "Not enough H1 history yet to classify volatility/trend regime."

    if atr_pct >= 90:
        return "HIGH_VOLATILITY", f"H1 ATR at the {atr_pct:.0f}th percentile of recent history."
    if atr_pct <= 10:
        return "LOW_VOLATILITY", f"H1 ATR at the {atr_pct:.0f}th percentile of recent history."

    trending = abs(ema_slope20) >= 0.15 and ((ema20 > ema50) == (ema_slope20 > 0))
    if trending:
        return ("TRENDING_UP" if ema_slope20 > 0 else "TRENDING_DOWN"), \
            f"H1 EMA20 sloping {'up' if ema_slope20 > 0 else 'down'} ({ema_slope20:.2f}% over 5 bars) with EMA20/50 aligned."

    if h1_structure.sequence == "MIXED" or h1_structure.sequence is None:
        return "RANGING", "H1 EMA slope flat and no clean swing structure — treating as range-bound."

    return "RANGING", "H1 EMA slope flat despite directional swing structure — insufficient trend strength."
