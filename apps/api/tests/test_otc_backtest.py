"""The backtester's own rules.

A backtester that is wrong is worse than no backtester: it produces a
number people act on. These cover the three things that decide whether
its output means anything -- that the outcome rule is right, that no
future data reaches the engine, and that the interval is honest.
"""

import sys
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, ".")
from otc_backtest import break_even, outcome, slice_closed, wilson

NOW = datetime(2026, 9, 8, 12, 0, tzinfo=timezone.utc)


def rising(count=20):
    return [{"open_time": NOW + timedelta(seconds=60 * i), "open": 100.0,
             "high": 100.0, "low": 100.0, "close": 100.0 + i} for i in range(count)]


def flat(count=20):
    return [{"open_time": NOW + timedelta(seconds=60 * i), "open": 1.0,
             "high": 1.0, "low": 1.0, "close": 1.0} for i in range(count)]


class OutcomeTests(unittest.TestCase):
    def test_call_into_a_rising_series_wins(self):
        self.assertEqual(outcome(rising(), NOW, 100.0, "CALL", 300), "WIN")

    def test_put_into_a_rising_series_loses(self):
        self.assertEqual(outcome(rising(), NOW, 100.0, "PUT", 300), "LOSS")

    def test_equal_close_is_a_draw(self):
        self.assertEqual(outcome(flat(), NOW, 1.0, "CALL", 300), "DRAW")
        self.assertEqual(outcome(rising(), NOW, 105.0, "CALL", 300), "DRAW")

    def test_no_bar_at_expiry_is_none_never_a_loss(self):
        """An outcome that cannot be observed is not one the engine got
        wrong. Counting it as a loss corrupts the rate downward exactly as
        much as dropping losses would corrupt it upward."""
        self.assertIsNone(outcome(rising(), NOW + timedelta(seconds=60 * 19),
                                  100.0, "CALL", 300))


class NoLookaheadTests(unittest.TestCase):
    def test_only_bars_closed_by_t_are_visible(self):
        sliced = slice_closed(rising(), NOW + timedelta(seconds=300), 60)
        self.assertEqual(len(sliced), 5)
        for row in sliced:
            self.assertLessEqual(row["open_time"], NOW + timedelta(seconds=240))

    def test_the_forming_bar_never_leaks(self):
        """The bar covering T itself has not finished, so it must be
        invisible -- this is the single rule that separates a backtest from
        a fantasy."""
        at = NOW + timedelta(seconds=330)
        sliced = slice_closed(rising(), at, 60)
        self.assertTrue(all(r["open_time"] + timedelta(seconds=60) <= at for r in sliced))


class IntervalTests(unittest.TestCase):
    def test_three_out_of_three_is_not_certainty(self):
        low, high = wilson(3, 3)
        self.assertLess(low, 50.0, "a perfect record on 3 trades must not read as proven")

    def test_interval_narrows_with_evidence(self):
        narrow = wilson(600, 1000)
        wide = wilson(6, 10)
        self.assertLess(narrow[1] - narrow[0], wide[1] - wide[0])

    def test_break_even_matches_the_payouts(self):
        self.assertAlmostEqual(break_even(0.80), 55.5556, places=3)
        self.assertAlmostEqual(break_even(0.91), 52.3560, places=3)

    def test_a_higher_payout_lowers_the_bar(self):
        self.assertLess(break_even(0.91), break_even(0.80))


if __name__ == "__main__":
    unittest.main()
