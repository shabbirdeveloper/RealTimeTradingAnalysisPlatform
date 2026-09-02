"""
The indicators added for spec sections 8 and 10.

These are checked against properties that must hold rather than against
numbers copied from a chart, because a hardcoded expected value only
proves the implementation still does what it did when the test was
written -- not that it is right.
"""

from __future__ import annotations

import unittest

from app.features import indicators as ind


def rising(n: int = 100, step: float = 1.0, start: float = 100.0) -> list[dict]:
    out = []
    p = start
    for _ in range(n):
        out.append({"open": p, "high": p + step, "low": p - step * 0.1, "close": p + step * 0.9})
        p += step
    return out


def falling(n: int = 100, step: float = 1.0, start: float = 200.0) -> list[dict]:
    out = []
    p = start
    for _ in range(n):
        out.append({"open": p, "high": p + step * 0.1, "low": p - step, "close": p - step * 0.9})
        p -= step
    return out


def choppy(n: int = 100, amplitude: float = 1.0, start: float = 100.0) -> list[dict]:
    out = []
    for i in range(n):
        p = start + (amplitude if i % 2 else -amplitude)
        out.append({"open": p, "high": p + 0.2, "low": p - 0.2, "close": p})
    return out


class AdxTests(unittest.TestCase):
    def test_insufficient_history_returns_none_not_a_guess(self):
        self.assertIsNone(ind.adx_latest(rising(10), period=14))

    def test_a_clean_trend_reads_as_trending(self):
        r = ind.adx_latest(rising(120))
        self.assertIsNotNone(r)
        self.assertTrue(r.trending, f"clean uptrend scored ADX {r.adx:.1f}")

    def test_chop_does_not_read_as_trending(self):
        r = ind.adx_latest(choppy(120))
        self.assertIsNotNone(r)
        self.assertFalse(r.trending, f"alternating candles scored ADX {r.adx:.1f}")

    def test_adx_is_direction_blind(self):
        """The whole reason to have ADX beside +DI/-DI: strength must not
        encode direction, or a strong downtrend reads as a weak uptrend."""
        up = ind.adx_latest(rising(120))
        down = ind.adx_latest(falling(120))
        self.assertAlmostEqual(up.adx, down.adx, delta=6.0)
        self.assertGreater(up.plus_di, up.minus_di)
        self.assertGreater(down.minus_di, down.plus_di)

    def test_directional_components_stay_in_range(self):
        for candles in (rising(120), falling(120), choppy(120)):
            r = ind.adx_latest(candles)
            for value in (r.adx, r.plus_di, r.minus_di):
                self.assertGreaterEqual(value, 0.0)
                self.assertLessEqual(value, 100.0)

    def test_rejects_a_nonsense_period(self):
        with self.assertRaises(ValueError):
            ind.adx_latest(rising(120), period=0)


class StochRsiTests(unittest.TestCase):
    def test_flat_rsi_is_undefined_not_neutral(self):
        """A zero-width range has no position within it. Returning 50 would
        read as 'neutral', which is a claim the data does not support."""
        flat = [100.0] * 120
        self.assertIsNone(ind.stoch_rsi_latest(flat))

    def test_a_perfectly_monotonic_rally_is_also_undefined(self):
        """Never a down bar means RSI pins at 100 for every bar, so its own
        range is zero-width. Undefined is the honest answer -- and this is
        why the fixture below has pullbacks, like real price does."""
        self.assertIsNone(ind.stoch_rsi_latest([100.0 + i for i in range(120)]))

    def test_a_rally_with_pullbacks_sits_near_the_top_of_its_own_range(self):
        values = [100.0]
        for i in range(1, 120):
            values.append(values[-1] + (1.5 if i % 5 else -0.6))
        v = ind.stoch_rsi_latest(values)
        self.assertIsNotNone(v)
        self.assertGreater(v, 60.0)

    def test_stays_inside_zero_to_one_hundred(self):
        values = [100.0 + (i % 7) - (i % 3) * 2 for i in range(200)]
        v = ind.stoch_rsi_latest(values)
        if v is not None:
            self.assertGreaterEqual(v, 0.0)
            self.assertLessEqual(v, 100.0)

    def test_short_history_returns_none(self):
        self.assertIsNone(ind.stoch_rsi_latest([100.0] * 10))


class RsiSeriesTests(unittest.TestCase):
    def test_series_last_value_matches_the_single_value_helper(self):
        """Two implementations of one thing is how they drift apart."""
        values = [100.0 + (i % 5) * 1.3 - (i % 3) for i in range(120)]
        series = [v for v in ind.rsi_series(values) if v is not None]
        self.assertAlmostEqual(series[-1], ind.rsi_latest(values), places=6)

    def test_warmup_entries_are_none_not_zero(self):
        values = [100.0 + i for i in range(50)]
        series = ind.rsi_series(values, period=14)
        self.assertTrue(all(v is None for v in series[:14]))
        self.assertIsNotNone(series[14])


class RateOfChangeTests(unittest.TestCase):
    def test_a_ten_percent_rise_reads_as_ten_percent(self):
        self.assertAlmostEqual(ind.rate_of_change([100.0] * 10 + [110.0], period=10), 10.0)

    def test_a_fall_is_negative(self):
        self.assertLess(ind.rate_of_change([100.0] * 10 + [90.0], period=10), 0)

    def test_zero_base_is_none_not_an_exception(self):
        self.assertIsNone(ind.rate_of_change([0.0] * 11, period=10))

    def test_short_history_returns_none(self):
        self.assertIsNone(ind.rate_of_change([100.0, 101.0], period=10))


class AccelerationTests(unittest.TestCase):
    def test_a_speeding_up_move_accelerates(self):
        values = [100.0]
        step = 0.5
        for _ in range(40):
            values.append(values[-1] + step)
            step *= 1.08
        self.assertGreater(ind.momentum_acceleration(values), 0)

    def test_a_fading_move_decelerates(self):
        values = [100.0]
        step = 3.0
        for _ in range(40):
            values.append(values[-1] + step)
            step *= 0.9
        self.assertLess(ind.momentum_acceleration(values), 0)

    def test_steady_drift_is_near_zero(self):
        values = [100.0 + i for i in range(60)]
        self.assertAlmostEqual(ind.momentum_acceleration(values), 0.0, delta=1.0)

    def test_short_history_returns_none(self):
        self.assertIsNone(ind.momentum_acceleration([100.0, 101.0, 102.0]))


if __name__ == "__main__":
    unittest.main()
