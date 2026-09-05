"""
Strategy C -- support/resistance rejection (spec Phase 18).

The idea: price reaches a zone that has held before, wicks through it, and
turns. This is the only one of the three that trades AGAINST the immediate
move, which makes it the one that must be most careful about context: a
rejection inside a strong opposing trend is usually just a pause.

So it requires the market NOT to be trending hard against the entry, and
it wants room on the other side. A rejection with the next zone sitting
half an ATR away has nowhere to go inside five minutes even when it is
read correctly.
"""

from __future__ import annotations

from app.features.levels import Zone, blocking_zone
from app.otc.features import MarketContext
from app.otc.strategies.base import SideScore, StrategyVerdict

# A zone must be at least this strong before a rejection off it is evidence.
_MIN_ZONE_STRENGTH = 55
# Price must be within this many ATRs of the zone to count as "at" it.
_AT_ZONE_ATR = 0.6


class LevelRejection:
    name = "level_rejection"

    def evaluate(self, context: MarketContext) -> StrategyVerdict:
        call, put = SideScore(), SideScore()
        warnings: list[str] = []

        structure = context.frame("M5")
        confirm = context.frame("M1")

        if structure is None or not structure.ready or structure.price is None:
            warnings.append("M5 not ready")
            return StrategyVerdict(self.name, call, put, warnings)

        support = _nearest(structure.zones, "SUPPORT")
        resistance = _nearest(structure.zones, "RESISTANCE")

        # --- at a level
        if support is not None and support.distance_atr <= _AT_ZONE_ATR:
            if support.strength >= _MIN_ZONE_STRENGTH:
                call.award("levels", 10, f"at support {support.price:.5f} (strength {support.strength}, {support.touches} touches)")
                call.award("structure", 12, "price testing an established support zone")
            else:
                warnings.append("support zone is weak")

        if resistance is not None and resistance.distance_atr <= _AT_ZONE_ATR:
            if resistance.strength >= _MIN_ZONE_STRENGTH:
                put.award("levels", 10, f"at resistance {resistance.price:.5f} (strength {resistance.strength}, {resistance.touches} touches)")
                put.award("structure", 12, "price testing an established resistance zone")
            else:
                warnings.append("resistance zone is weak")

        # --- the rejection itself: a wick through the level that closed back
        if structure.shape is not None:
            shape = structure.shape
            if shape.lower_wick_ratio >= 0.45 and call.levels:
                call.award("price_action", 15, f"lower wick rejection ({shape.lower_wick_ratio:.0%} of range)")
            if shape.upper_wick_ratio >= 0.45 and put.levels:
                put.award("price_action", 15, f"upper wick rejection ({shape.upper_wick_ratio:.0%} of range)")

        if confirm is not None and confirm.sequence is not None:
            pressure = confirm.sequence.wick_pressure
            if pressure > 0.2:
                call.award("price_action", 6, f"M1 buyers defending wicks ({pressure:+.2f})")
            elif pressure < -0.2:
                put.award("price_action", 6, f"M1 sellers pressing wicks ({pressure:+.2f})")

        # --- momentum turning, not merely opposite
        if confirm is not None and confirm.rsi is not None and confirm.rsi_direction:
            if confirm.rsi < 40 and confirm.rsi_direction == "RISING":
                call.award("momentum", 20, f"M1 RSI turning up from {confirm.rsi:.0f}")
            if confirm.rsi > 60 and confirm.rsi_direction == "FALLING":
                put.award("momentum", 20, f"M1 RSI turning down from {confirm.rsi:.0f}")

        # --- context veto: do not fade a market that is trending hard
        sep = structure.ema_separation
        if sep is not None:
            if sep > 0.5:
                warnings.append("M5 trending up strongly -- fading it is low quality")
                put.trend = 0
                put.momentum = min(put.momentum, 5)
            elif sep < -0.5:
                warnings.append("M5 trending down strongly -- fading it is low quality")
                call.trend = 0
                call.momentum = min(call.momentum, 5)
            elif abs(sep) < 0.25:
                # A flat market is where rejections work best.
                call.award("trend", 12, "M5 not trending -- rejection conditions")
                put.award("trend", 12, "M5 not trending -- rejection conditions")

        # --- room to travel
        if blocking_zone(structure.zones, "CALL", within_atr=1.0) is not None:
            warnings.append("resistance within 1 ATR above -- limited room for a CALL")
            call.levels = min(call.levels, 4)
        if blocking_zone(structure.zones, "PUT", within_atr=1.0) is not None:
            warnings.append("support within 1 ATR below -- limited room for a PUT")
            put.levels = min(put.levels, 4)

        # --- volatility: rejections need range, but not a runaway tape
        if structure.atr_pct is not None and 20.0 <= structure.atr_pct <= 75.0:
            call.award("volatility", 10, f"M5 ATR {structure.atr_pct:.0f}th percentile")
            put.award("volatility", 10, f"M5 ATR {structure.atr_pct:.0f}th percentile")

        return StrategyVerdict(self.name, call, put, warnings)


def _nearest(zones: list[Zone], kind: str) -> Zone | None:
    matches = [z for z in zones if z.kind == kind]
    return min(matches, key=lambda z: z.distance_atr) if matches else None
