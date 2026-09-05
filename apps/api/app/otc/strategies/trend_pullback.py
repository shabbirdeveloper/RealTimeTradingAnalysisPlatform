"""
Strategy A -- trend pullback continuation (spec Phase 18).

The idea: an established trend that has retraced into its own fast average
and is starting to turn back. It is the highest-quality setup available to
a 5-minute expiry, because the retracement supplies both a defined level
and room to travel before the next obstacle.

The failure it must avoid is entering a retracement that is actually a
reversal. That is what the structure requirement is for: the pullback is
only tradeable while the higher-timeframe sequence still holds. Once the
sequence breaks, the same price action is a trend ending, and every
feature that made it look attractive still looks attractive.
"""

from __future__ import annotations

from app.otc.features import MarketContext, TimeframeFeatures
from app.otc.strategies.base import SideScore, StrategyVerdict


# Pattern vocabulary comes from app.features.price_action.patterns(). Named
# here rather than inline so a rename there fails loudly in one place
# instead of silently matching nothing in three strategies.
BULLISH_CONFIRMATION = {"BULLISH_ENGULFING", "HAMMER", "STRONG_BULL_BODY"}
BEARISH_CONFIRMATION = {"BEARISH_ENGULFING", "SHOOTING_STAR", "STRONG_BEAR_BODY"}


class TrendPullback:
    name = "trend_pullback"

    def evaluate(self, context: MarketContext) -> StrategyVerdict:
        call, put = SideScore(), SideScore()
        warnings: list[str] = []

        ctx = context.frame("M15")
        structure = context.frame("M5")
        momentum = context.frame("M3")
        confirm = context.frame("M1")

        if structure is None or not structure.ready:
            warnings.append("M5 not ready")
            return StrategyVerdict(self.name, call, put, warnings)

        # --- trend: the M15 context and the M5 trend must point the same way
        for side, up in ((call, True), (put, False)):
            if _trending(ctx, up=up) and _trending(structure, up=up):
                side.award("trend", 20, f"M15 and M5 both {'bullish' if up else 'bearish'}")
            elif _trending(structure, up=up):
                side.award("trend", 10, f"M5 {'bullish' if up else 'bearish'}, M15 unclear")

        if ctx is not None and structure is not None:
            if _trending(ctx, up=True) and _trending(structure, up=False):
                warnings.append("M15 bullish against M5 bearish")
            elif _trending(ctx, up=False) and _trending(structure, up=True):
                warnings.append("M15 bearish against M5 bullish")

        # --- structure: the sequence that makes this a pullback and not a top
        seq = structure.structure.sequence
        if seq == "HH_HL":
            call.award("structure", 20, "M5 higher highs and higher lows")
        elif seq == "LH_LL":
            put.award("structure", 20, "M5 lower highs and lower lows")
        elif seq == "MIXED":
            warnings.append("M5 structure mixed")

        if structure.structure.choch:
            warnings.append("M5 change of character -- the trend may be ending")

        # --- the pullback itself: price back at EMA21 while trend holds
        pull = structure.price_vs_ema21
        if pull is not None:
            if seq == "HH_HL" and -1.2 <= pull <= 0.35:
                call.award("levels", 10, f"price retraced to EMA21 ({pull:+.2f} ATR)")
            if seq == "LH_LL" and -0.35 <= pull <= 1.2:
                put.award("levels", 10, f"price retraced to EMA21 ({pull:+.2f} ATR)")

        # --- momentum must be RECOVERING, not merely present. A pullback
        # with momentum still falling is a pullback still in progress.
        if momentum is not None and momentum.macd_hist_change is not None:
            if momentum.macd_hist_change > 0:
                call.award("momentum", 20, "M3 MACD histogram rising")
            elif momentum.macd_hist_change < 0:
                put.award("momentum", 20, "M3 MACD histogram falling")

        # --- confirmation candle on M1
        if confirm is not None and confirm.shape is not None:
            if BULLISH_CONFIRMATION & set(confirm.patterns):
                call.award("price_action", 15, "M1 bullish confirmation candle")
            if BEARISH_CONFIRMATION & set(confirm.patterns):
                put.award("price_action", 15, "M1 bearish confirmation candle")

        # --- volatility: this setup needs range to travel into
        if structure.atr_pct is not None and 25.0 <= structure.atr_pct <= 80.0:
            call.award("volatility", 10, f"M5 ATR in a workable {structure.atr_pct:.0f}th percentile")
            put.award("volatility", 10, f"M5 ATR in a workable {structure.atr_pct:.0f}th percentile")

        return StrategyVerdict(self.name, call, put, warnings)


def _trending(frame: TimeframeFeatures | None, *, up: bool) -> bool:
    if frame is None or not frame.ready:
        return False
    sep = frame.ema_separation
    above = frame.price_vs_ema50
    if sep is None or above is None:
        return False
    return (sep > 0.15 and above > 0) if up else (sep < -0.15 and above < 0)
