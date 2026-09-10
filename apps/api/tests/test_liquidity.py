"""Liquidity sweep detection (brief section 7).

Built on hand-constructed candles rather than generated ones, because
these rules are geometric: the test should say which shape it is
describing, and a failure should name the shape that stopped working.

The look-ahead test is the important one. A sweep detector that lets the
sweep candle confirm the swing it is sweeping produces beautiful history
that could not have been seen at the time, and every backtest built on it
reports an edge that is not there.
"""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from app.otc.liquidity import (
    DEFAULT_SWEEP_CONFIG,
    SweepConfig,
    anatomy,
    detect_sweep,
)

T0 = datetime(2026, 9, 10, 9, 0, tzinfo=timezone.utc)


def bar(i: int, o: float, h: float, l: float, c: float) -> dict:
    return {"open_time": T0 + timedelta(minutes=5 * i),
            "open": o, "high": h, "low": l, "close": c}


def flat(count: int, base: float = 100.0, spread: float = 1.0, start: int = 0) -> list[dict]:
    """Quiet oscillating bars — a background with a stable ATR and no
    swing extreme deep enough to be mistaken for the planted one."""
    out = []
    for i in range(count):
        drift = 0.2 if i % 2 else -0.2
        o = base + drift
        c = base - drift
        out.append(bar(start + i, o, max(o, c) + spread, min(o, c) - spread, c))
    return out


class AnatomyTests(unittest.TestCase):
    def test_measurements_match_the_definitions(self):
        a = anatomy(bar(0, o=100.0, h=110.0, l=90.0, c=104.0))
        self.assertEqual(a.body, 4.0)
        self.assertEqual(a.upper_wick, 6.0)     # 110 - max(100, 104)
        self.assertEqual(a.lower_wick, 10.0)    # min(100, 104) - 90
        self.assertEqual(a.range_, 20.0)
        self.assertAlmostEqual(a.close_location, 0.7)
        self.assertTrue(a.bullish)

    def test_a_zero_range_candle_does_not_divide_by_zero(self):
        a = anatomy(bar(0, 100.0, 100.0, 100.0, 100.0))
        self.assertEqual(a.range_, 0.0)
        self.assertEqual(a.body_ratio, 0.0)
        self.assertEqual(a.close_location, 0.5)


class BullishSweepTests(unittest.TestCase):
    def _market(self) -> list[dict]:
        candles = flat(12)
        # A confirmed swing low at index 12, with quiet bars either side so
        # the fractal window can see it.
        candles.append(bar(12, 100.0, 101.0, 94.0, 100.5))
        candles += flat(6, start=13)
        return candles

    def test_a_wick_through_the_low_that_closes_back_above_is_a_sweep(self):
        candles = self._market()
        # Pierces 94, closes near its high — the shape the rule describes.
        candles.append(bar(19, 99.0, 100.5, 92.0, 100.0))
        sweep = detect_sweep(candles)
        self.assertIsNotNone(sweep, "a clean bullish sweep was not detected")
        self.assertEqual(sweep.direction, "BULLISH")
        self.assertAlmostEqual(sweep.level, 94.0)
        self.assertGreater(sweep.strength, 0)

    def test_closing_below_the_level_is_a_breakdown_not_a_sweep(self):
        """The level was taken and NOT reclaimed. Calling this a bullish
        sweep would trade straight into a breakdown."""
        candles = self._market()
        candles.append(bar(19, 99.0, 99.5, 92.0, 92.5))
        self.assertIsNone(detect_sweep(candles))

    def test_a_one_tick_graze_is_not_a_sweep(self):
        """Below the ATR floor: too shallow to have taken any orders."""
        candles = self._market()
        candles.append(bar(19, 99.0, 100.5, 93.98, 100.0))
        self.assertIsNone(detect_sweep(candles))

    def test_a_body_dominant_candle_is_not_a_rejection(self):
        candles = self._market()
        # Big bullish body, almost no lower wick beyond the level.
        candles.append(bar(19, 93.0, 101.0, 92.5, 100.8))
        sweep = detect_sweep(candles)
        self.assertIsNone(sweep, "a body-dominant candle must not count as rejection")


class BearishSweepTests(unittest.TestCase):
    def _market(self) -> list[dict]:
        candles = flat(12)
        candles.append(bar(12, 100.0, 106.0, 99.0, 99.5))
        candles += flat(6, start=13)
        return candles

    def test_a_wick_above_the_high_that_closes_back_below_is_a_sweep(self):
        candles = self._market()
        candles.append(bar(19, 101.0, 108.0, 99.5, 100.0))
        sweep = detect_sweep(candles)
        self.assertIsNotNone(sweep, "a clean bearish sweep was not detected")
        self.assertEqual(sweep.direction, "BEARISH")
        self.assertAlmostEqual(sweep.level, 106.0)

    def test_closing_above_the_level_is_a_breakout_not_a_sweep(self):
        candles = self._market()
        candles.append(bar(19, 101.0, 108.0, 100.5, 107.5))
        self.assertIsNone(detect_sweep(candles))


class LookaheadTests(unittest.TestCase):
    """The rule the whole module depends on."""

    def test_the_sweep_candle_cannot_confirm_the_swing_it_sweeps(self):
        # A low placed so close to the end that only the sweep candle
        # could complete its fractal window. It must be invisible.
        candles = flat(12)
        candles.append(bar(12, 100.0, 101.0, 94.0, 100.5))
        candles.append(bar(13, 100.0, 101.0, 99.0, 100.5))   # window = 2 needs two
        candles.append(bar(14, 99.0, 100.5, 92.0, 100.0))    # the sweep, at +2
        self.assertIsNone(
            detect_sweep(candles),
            "a swing confirmed only by the sweep candle's own position was used",
        )

    def test_the_same_swing_is_usable_once_it_is_genuinely_confirmed(self):
        """The mirror of the test above: with one more bar of separation
        the swing is real history and the sweep counts. Without this pair,
        a detector that never fires would pass the look-ahead test."""
        candles = flat(12)
        candles.append(bar(12, 100.0, 101.0, 94.0, 100.5))
        candles += flat(3, start=13)
        candles.append(bar(16, 99.0, 100.5, 92.0, 100.0))
        self.assertIsNotNone(detect_sweep(candles))

    def test_an_old_level_falls_out_of_the_lookback(self):
        candles = flat(6)
        candles.append(bar(6, 100.0, 101.0, 94.0, 100.5))
        candles += flat(60, start=7)
        candles.append(bar(67, 99.0, 100.5, 92.0, 100.0))
        self.assertIsNone(detect_sweep(candles), "a level 60 bars old should have expired")


class TwoSidedTests(unittest.TestCase):
    def test_a_candle_that_sweeps_both_sides_commits_to_neither(self):
        """An outside bar closing mid-range took liquidity in both
        directions. Picking the 'stronger' side would manufacture a
        direction out of a genuinely two-sided candle."""
        candles = flat(10)
        candles.append(bar(10, 100.0, 106.0, 99.0, 99.5))    # swing high
        candles += flat(2, start=11)
        candles.append(bar(13, 100.0, 101.0, 94.0, 100.5))   # swing low
        candles += flat(3, start=14)
        candles.append(bar(17, 100.0, 108.0, 92.0, 100.0))   # pierces both
        self.assertIsNone(detect_sweep(candles))


class ConfigTests(unittest.TestCase):
    def test_every_threshold_is_configurable(self):
        """Brief section 23: no magic numbers scattered through the code."""
        for field in ("swing_window", "lookback", "min_wick_ratio",
                      "min_penetration_atr", "max_penetration_atr",
                      "min_close_location", "max_body_ratio"):
            self.assertTrue(hasattr(DEFAULT_SWEEP_CONFIG, field), field)

    def test_a_stricter_wick_requirement_rejects_a_marginal_sweep(self):
        candles = flat(12)
        candles.append(bar(12, 100.0, 101.0, 94.0, 100.5))
        candles += flat(6, start=13)
        candles.append(bar(19, 99.0, 100.5, 92.0, 100.0))
        self.assertIsNotNone(detect_sweep(candles))
        strict = SweepConfig(min_wick_ratio=0.95)
        self.assertIsNone(detect_sweep(candles, config=strict))

    def test_insufficient_history_returns_none_rather_than_guessing(self):
        self.assertIsNone(detect_sweep(flat(3)))


if __name__ == "__main__":
    unittest.main()
