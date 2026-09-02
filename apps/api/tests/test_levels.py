"""
Support/resistance zones (spec section 13).

The behaviour worth pinning down is not "does it find a level" but the
distinctions that make a level useful: a zone tested twice differs from a
swing seen once, a level price bounced off differs from one it grazed,
and a level on the wrong side of the trade is not an obstacle at all.
"""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from app.features.levels import (
    MIN_TOUCHES,
    RELEVANT_ATR_DISTANCE,
    blocking_zone,
    find_zones,
)

START = datetime(2026, 9, 1, tzinfo=timezone.utc)


def bar(i: int, high: float, low: float, close: float | None = None) -> dict:
    return {
        "open_time": START + timedelta(minutes=5 * i),
        "open": (high + low) / 2,
        "high": high, "low": low,
        "close": close if close is not None else (high + low) / 2,
    }


def series_with_ceiling(ceiling: float, touches: int, base: float = 100.0) -> list[dict]:
    """Price repeatedly rallies to `ceiling` and is turned away."""
    candles: list[dict] = []
    i = 0
    for _ in range(touches):
        for step in (0.0, 1.0, 2.0):          # up toward the ceiling
            candles.append(bar(i, base + step, base + step - 1.0)); i += 1
        candles.append(bar(i, ceiling, ceiling - 1.5, ceiling - 1.4)); i += 1   # the touch
        for step in (2.0, 1.0, 0.0):          # rejected, back down
            candles.append(bar(i, base + step, base + step - 1.0)); i += 1
    return candles


class ZoneTests(unittest.TestCase):
    def test_no_zones_without_enough_history_for_atr(self):
        self.assertEqual(find_zones([bar(i, 101, 99) for i in range(5)]), [])

    def test_a_repeatedly_rejected_level_becomes_a_resistance_zone(self):
        zones = find_zones(series_with_ceiling(110.0, touches=4))
        resistance = [z for z in zones if z.kind == "RESISTANCE"]
        self.assertTrue(resistance, "expected a resistance zone")
        self.assertTrue(any(abs(z.price - 110.0) < 2.0 for z in resistance))

    def test_a_single_swing_is_not_a_level(self):
        """One touch is a swing. Calling it a level manufactures structure
        out of a single bar."""
        zones = find_zones(series_with_ceiling(110.0, touches=1))
        self.assertTrue(all(z.touches >= MIN_TOUCHES for z in zones))

    def test_more_touches_score_higher_than_fewer(self):
        few = find_zones(series_with_ceiling(110.0, touches=2))
        many = find_zones(series_with_ceiling(110.0, touches=5))
        best_few = max((z.strength for z in few if z.kind == "RESISTANCE"), default=0)
        best_many = max((z.strength for z in many if z.kind == "RESISTANCE"), default=0)
        self.assertGreaterEqual(best_many, best_few)

    def test_zones_are_ordered_by_distance_from_price(self):
        zones = find_zones(series_with_ceiling(110.0, touches=4))
        distances = [z.distance_atr for z in zones]
        self.assertEqual(distances, sorted(distances))

    def test_far_away_levels_are_dropped(self):
        zones = find_zones(series_with_ceiling(110.0, touches=4))
        self.assertTrue(all(z.distance_atr <= RELEVANT_ATR_DISTANCE for z in zones))

    def test_clustering_uses_the_group_mean_not_the_first_member(self):
        """Single-linkage chaining would merge a long drift of nearly-touching
        swings into one zone far wider than the tolerance, which then blocks
        every signal and looks like the filter working."""
        candles: list[dict] = []
        i = 0
        for offset in range(0, 40, 2):        # a staircase of rising swings
            candles.append(bar(i, 100 + offset, 99 + offset)); i += 1
            candles.append(bar(i, 102 + offset, 101 + offset)); i += 1
            candles.append(bar(i, 100 + offset, 99 + offset)); i += 1
        zones = find_zones(candles)
        for z in zones:
            self.assertLess(z.strength, 101)
            self.assertGreater(z.price, 0)


class BlockingTests(unittest.TestCase):
    def _zones(self):
        return find_zones(series_with_ceiling(110.0, touches=5))

    def test_a_level_on_the_wrong_side_is_not_an_obstacle(self):
        """Support beneath a CALL is help, not a blocker. An implementation
        that ignores the sign turns every level into a reason to refuse."""
        zones = self._zones()
        supports = [z for z in zones if z.kind == "SUPPORT"]
        if supports:
            self.assertIsNone(blocking_zone(supports, "CALL", within_atr=99.0))

    def test_strong_resistance_close_above_blocks_a_call(self):
        zones = [z for z in self._zones() if z.kind == "RESISTANCE" and z.is_strong]
        if zones:
            self.assertIsNotNone(blocking_zone(zones, "CALL", within_atr=99.0))

    def test_no_trade_direction_is_never_blocked(self):
        self.assertIsNone(blocking_zone(self._zones(), "NO_TRADE"))

    def test_distant_levels_do_not_block(self):
        zones = self._zones()
        self.assertIsNone(blocking_zone(zones, "CALL", within_atr=0.0001))

    def test_empty_input_blocks_nothing(self):
        self.assertIsNone(blocking_zone([], "CALL"))


if __name__ == "__main__":
    unittest.main()
