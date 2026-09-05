"""
Strategy B -- momentum continuation (spec Phase 18).

The idea: a trend already moving, with momentum strengthening across the
lower timeframes, entered in the direction it is already travelling.

The failure mode is the mirror of Strategy A's. A pullback strategy can
enter a reversal; a momentum strategy can enter an exhaustion -- the last
candle of a move, where every momentum reading is at its most attractive
precisely because the move is finishing. So this strategy spends most of
its logic refusing overextension rather than detecting momentum, which is
the easy half.
"""

from __future__ import annotations

from app.otc.features import MarketContext, TimeframeFeatures
from app.otc.strategies.base import SideScore, StrategyVerdict

# Beyond this distance from EMA21, in ATRs, price has already travelled the
# distance a 5-minute expiry was supposed to capture.
_OVEREXTENDED_ATR = 2.0
# RSI beyond these bounds on the confirmation timeframe is late, not strong.
_RSI_OVERBOUGHT = 78.0
_RSI_OVERSOLD = 22.0


class MomentumContinuation:
    name = "momentum_continuation"

    def evaluate(self, context: MarketContext) -> StrategyVerdict:
        call, put = SideScore(), SideScore()
        warnings: list[str] = []

        structure = context.frame("M5")
        momentum = context.frame("M3")
        confirm = context.frame("M1")

        if structure is None or momentum is None or not structure.ready:
            warnings.append("M5/M3 not ready")
            return StrategyVerdict(self.name, call, put, warnings)

        # --- trend: M5 direction, weighted by how convincingly the EMAs
        # have separated rather than merely which side they are on
        sep = structure.ema_separation
        if sep is not None:
            if sep > 0.15:
                call.award("trend", min(20, int(sep * 30)), f"M5 EMA9 above EMA21 by {sep:.2f} ATR")
            elif sep < -0.15:
                put.award("trend", min(20, int(-sep * 30)), f"M5 EMA9 below EMA21 by {-sep:.2f} ATR")

        # --- structure
        seq = structure.structure.sequence
        if seq == "HH_HL":
            call.award("structure", 15, "M5 higher highs and higher lows")
        elif seq == "LH_LL":
            put.award("structure", 15, "M5 lower highs and lower lows")
        if structure.structure.bos:
            leader = call if seq == "HH_HL" else put if seq == "LH_LL" else None
            if leader is not None:
                leader.award("structure", 5, "M5 break of structure in the trend direction")

        # --- momentum strengthening: level AND direction, both required.
        # A positive histogram that is shrinking is a move losing its
        # engine, which reads identically to a healthy one if you only
        # check the sign.
        if momentum.macd_hist is not None and momentum.macd_hist_change is not None:
            if momentum.macd_hist > 0 and momentum.macd_hist_change > 0:
                call.award("momentum", 14, "M3 MACD positive and building")
            elif momentum.macd_hist < 0 and momentum.macd_hist_change < 0:
                put.award("momentum", 14, "M3 MACD negative and building")
            elif momentum.macd_hist > 0 and momentum.macd_hist_change < 0:
                warnings.append("M3 bullish momentum is fading")
            elif momentum.macd_hist < 0 and momentum.macd_hist_change > 0:
                warnings.append("M3 bearish momentum is fading")

        if momentum.ema9_slope is not None:
            if momentum.ema9_slope > 0:
                call.award("momentum", 6, "M3 EMA9 sloping up")
            elif momentum.ema9_slope < 0:
                put.award("momentum", 6, "M3 EMA9 sloping down")

        # --- M1 confirmation: continuation, not reversal
        if confirm is not None and confirm.sequence is not None:
            # -1.0 (all down) .. +1.0 (all up), so scale across the whole
            # 15-point budget rather than treating it as a candle count.
            persistence = confirm.sequence.directional_persistence
            if persistence > 0.2:
                call.award("price_action", int(persistence * 15),
                           f"M1 closes persistently bullish ({persistence:+.2f})")
            elif persistence < -0.2:
                put.award("price_action", int(-persistence * 15),
                          f"M1 closes persistently bearish ({persistence:+.2f})")

        # --- overextension: the veto this strategy exists to apply
        extension = structure.price_vs_ema21
        if extension is not None and abs(extension) >= _OVEREXTENDED_ATR:
            warnings.append(f"price {abs(extension):.1f} ATR from M5 EMA21 -- overextended")
            _strip(call if extension > 0 else put, "momentum")

        if confirm is not None and confirm.rsi is not None:
            if confirm.rsi >= _RSI_OVERBOUGHT:
                warnings.append(f"M1 RSI {confirm.rsi:.0f} -- late to buy")
                _strip(call, "momentum")
            elif confirm.rsi <= _RSI_OVERSOLD:
                warnings.append(f"M1 RSI {confirm.rsi:.0f} -- late to sell")
                _strip(put, "momentum")

        # --- volatility: momentum needs expansion, not a dead tape
        if structure.atr_pct is not None and 35.0 <= structure.atr_pct <= 90.0:
            call.award("volatility", 10, f"M5 ATR expanding ({structure.atr_pct:.0f}th percentile)")
            put.award("volatility", 10, f"M5 ATR expanding ({structure.atr_pct:.0f}th percentile)")
        elif structure.atr_pct is not None and structure.atr_pct < 20.0:
            warnings.append("volatility too low for a momentum entry")

        return StrategyVerdict(self.name, call, put, warnings)


def _strip(side: SideScore, category: str) -> None:
    """Remove a category's points after a veto. Zeroing the category rather
    than subtracting a fixed penalty means an overextended market cannot
    still score well on the very evidence that made it overextended."""
    setattr(side, category, 0)


def _ready(frame: TimeframeFeatures | None) -> bool:
    return frame is not None and frame.ready
