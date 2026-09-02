"""
Candle anatomy, patterns and sequences (spec sections 14 and 15).
"""

from __future__ import annotations

import unittest

from app.features.price_action import (
    SequenceReading,
    patterns,
    sequence,
    shape_of,
)


def c(o: float, h: float, l: float, cl: float) -> dict:
    return {"open": o, "high": h, "low": l, "close": cl}


class ShapeTests(unittest.TestCase):
    def test_a_zero_range_candle_does_not_divide_by_zero(self):
        """An illiquid minute really does print these."""
        s = shape_of(c(100, 100, 100, 100))
        self.assertEqual(s.range_size, 0.0)
        self.assertEqual(s.close_location, 0.5)

    def test_ratios_are_scale_free(self):
        """The same shape at 1.16 and at 4300 must read identically, or a
        detector works on one instrument and silently fails on the other."""
        small = shape_of(c(1.1600, 1.1610, 1.1590, 1.1608))
        large = shape_of(c(4300.0, 4400.0, 4200.0, 4380.0))
        self.assertAlmostEqual(small.close_location, large.close_location, places=6)
        self.assertAlmostEqual(small.body_ratio, large.body_ratio, places=6)

    def test_close_location_is_one_at_the_high_and_zero_at_the_low(self):
        self.assertAlmostEqual(shape_of(c(100, 110, 100, 110)).close_location, 1.0)
        self.assertAlmostEqual(shape_of(c(110, 110, 100, 100)).close_location, 0.0)

    def test_all_ratios_stay_within_zero_and_one(self):
        for candle in (c(100, 110, 90, 105), c(105, 106, 95, 96), c(100, 100.1, 99.9, 100)):
            s = shape_of(candle)
            for value in (s.body_ratio, s.upper_wick_ratio, s.lower_wick_ratio, s.close_location):
                self.assertGreaterEqual(value, 0.0)
                self.assertLessEqual(value, 1.0)

    def test_body_and_wicks_account_for_the_whole_range(self):
        s = shape_of(c(101, 110, 99, 107))
        self.assertAlmostEqual(s.body_ratio + s.upper_wick_ratio + s.lower_wick_ratio, 1.0, places=9)


class PatternTests(unittest.TestCase):
    def test_engulfing_compares_bodies_not_ranges(self):
        """Comparing high-to-low instead turns every outside bar into an
        engulfing, which is the most common way this detector goes wrong."""
        # Outside bar by range, but the body does not engulf.
        found = patterns([c(100, 101, 99, 100.5), c(100.6, 105, 95, 100.4)])
        self.assertNotIn("BULLISH_ENGULFING", found)
        self.assertIn("OUTSIDE_BAR", found)

    def test_a_real_bullish_engulfing_is_detected(self):
        found = patterns([c(102, 102.5, 99, 99.5), c(99, 103.5, 98.8, 103)])
        self.assertIn("BULLISH_ENGULFING", found)

    def test_a_real_bearish_engulfing_is_detected(self):
        found = patterns([c(99, 102.5, 98.5, 102), c(102.5, 103, 98, 98.5)])
        self.assertIn("BEARISH_ENGULFING", found)

    def test_a_long_lower_wick_is_a_hammer(self):
        self.assertIn("HAMMER", patterns([c(100, 101, 99, 100), c(100, 100.4, 96, 100.1)]))

    def test_a_long_upper_wick_is_a_shooting_star(self):
        self.assertIn("SHOOTING_STAR", patterns([c(100, 101, 99, 100), c(100, 104, 99.7, 99.9)]))

    def test_a_tiny_body_is_a_doji(self):
        self.assertIn("DOJI", patterns([c(100, 101, 99, 100), c(100, 102, 98, 100.05)]))

    def test_inside_and_outside_bars_are_mutually_exclusive(self):
        inside = patterns([c(100, 105, 95, 100), c(100, 103, 97, 101)])
        outside = patterns([c(100, 103, 97, 100), c(100, 105, 95, 101)])
        self.assertIn("INSIDE_BAR", inside)
        self.assertNotIn("OUTSIDE_BAR", inside)
        self.assertIn("OUTSIDE_BAR", outside)
        self.assertNotIn("INSIDE_BAR", outside)

    def test_every_matching_pattern_is_reported_not_only_one(self):
        """A candle can be two things at once, and picking a winner throws
        away half of what was seen."""
        found = patterns([c(102, 102.5, 99, 99.2), c(99, 104, 98.9, 103.8)])
        self.assertIn("BULLISH_ENGULFING", found)
        self.assertIn("STRONG_BULL_BODY", found)

    def test_a_single_candle_yields_nothing(self):
        self.assertEqual(patterns([c(100, 101, 99, 100)]), [])


class SequenceTests(unittest.TestCase):
    def test_too_little_history_returns_none(self):
        self.assertIsNone(sequence([c(100, 101, 99, 100)], window=5))

    def test_a_run_of_up_candles_has_full_positive_persistence(self):
        s = sequence([c(100 + i, 101 + i, 99 + i, 100.8 + i) for i in range(5)], window=5)
        self.assertEqual(s.directional_persistence, 1.0)
        self.assertEqual(s.bearish_count, 0)

    def test_a_run_of_down_candles_has_full_negative_persistence(self):
        s = sequence([c(100 - i, 101 - i, 99 - i, 99.2 - i) for i in range(5)], window=5)
        self.assertEqual(s.directional_persistence, -1.0)

    def test_wick_pressure_reflects_where_closes_sat_not_candle_colour(self):
        """Closing near the high repeatedly means buyers held each bar,
        which is a different fact from the bars being green."""
        high_closes = sequence([c(100, 101, 99, 100.95) for _ in range(5)], window=5)
        low_closes = sequence([c(100, 101, 99, 99.05) for _ in range(5)], window=5)
        self.assertGreater(high_closes.wick_pressure, 0.8)
        self.assertLess(low_closes.wick_pressure, -0.8)

    def test_alternating_small_candles_read_as_indecisive(self):
        candles = []
        for i in range(6):
            candles.append(c(100, 102, 98, 100.1 if i % 2 else 99.9))
        self.assertTrue(sequence(candles, window=6).indecisive)

    def test_a_strong_trend_is_not_indecisive(self):
        s = sequence([c(100 + i, 100.9 + i, 99.9 + i, 100.85 + i) for i in range(5)], window=5)
        self.assertFalse(s.indecisive)

    def test_window_must_be_positive(self):
        with self.assertRaises(ValueError):
            sequence([c(100, 101, 99, 100)] * 5, window=0)

    def test_persistence_is_bounded(self):
        for n in (3, 5, 10):
            s = sequence([c(100, 101, 99, 100.5) for _ in range(n)], window=n)
            self.assertGreaterEqual(s.directional_persistence, -1.0)
            self.assertLessEqual(s.directional_persistence, 1.0)
            self.assertIsInstance(s, SequenceReading)


if __name__ == "__main__":
    unittest.main()
