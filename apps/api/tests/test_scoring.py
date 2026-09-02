"""
The point of scoring both sides is to preserve distinctions the old netted
score destroyed, so those distinctions are what these tests assert.
"""

from __future__ import annotations

import unittest

from app.features.scoring import VOTERS_PER_TIMEFRAME, SideScores, side_scores
from app.features.timeframe_bias import TimeframeBias


def tf(name: str, bull: int, bear: int, *, insufficient: bool = False) -> TimeframeBias:
    return TimeframeBias(
        timeframe=name, bias="X", strength=0,
        bull_votes=bull, bear_votes=bear, insufficient_data=insufficient,
    )


class SeparationTests(unittest.TestCase):
    def test_conflict_and_thin_evidence_are_distinguishable(self):
        """The whole reason this module exists.

        Three voters up against two down nets to +1, and so does one up
        against none. Under the old netted score they were the same number.
        A market arguing with itself and a market with almost no evidence
        call for the same decision -- no trade -- but for opposite reasons,
        and tuning cannot tell them apart if scoring cannot.
        """
        conflicted = side_scores([tf("M5", 3, 2)])
        thin = side_scores([tf("M5", 1, 0)])

        self.assertNotEqual((conflicted.call, conflicted.put), (thin.call, thin.put))
        # Conflict shows up as a high uncommitted-free split...
        self.assertEqual((conflicted.call, conflicted.put), (60, 40))
        # ...thin evidence as most of the scale unclaimed.
        self.assertEqual(thin.uncommitted, 80)
        self.assertLess(conflicted.uncommitted, thin.uncommitted)

    def test_scores_are_not_complements(self):
        """put = 100 - call would manufacture conviction out of silence."""
        s = side_scores([tf("M5", 1, 0)])
        self.assertNotEqual(s.put, 100 - s.call)
        self.assertEqual(s.put, 0)

    def test_unanimous_agreement_reaches_the_top_of_the_scale(self):
        s = side_scores([tf("M5", VOTERS_PER_TIMEFRAME, 0), tf("M15", VOTERS_PER_TIMEFRAME, 0)])
        self.assertEqual((s.call, s.put), (100, 0))
        self.assertEqual(s.difference, 100)
        self.assertEqual(s.leader, "CALL")

    def test_timeframes_pointing_opposite_ways_cancel_to_no_leader(self):
        s = side_scores([tf("H4", 4, 0), tf("M5", 0, 4)])
        self.assertEqual(s.call, s.put)
        self.assertEqual(s.difference, 0)
        self.assertEqual(s.leader, "NO_TRADE")

    def test_silence_scores_zero_on_both_sides_not_fifty_fifty(self):
        s = side_scores([tf("M5", 0, 0), tf("M15", 0, 0)])
        self.assertEqual((s.call, s.put), (0, 0))
        self.assertEqual(s.uncommitted, 100)

    def test_warmup_gaps_are_excluded_rather_than_counted_neutral(self):
        """Missing evidence is not evidence of balance. A timeframe still
        warming up must not dilute the sides toward a tie."""
        with_gap = side_scores([tf("M5", 5, 0), tf("H4", 0, 0, insufficient=True)])
        alone = side_scores([tf("M5", 5, 0)])
        self.assertEqual((with_gap.call, with_gap.put), (alone.call, alone.put))

    def test_no_usable_timeframes_scores_zero(self):
        self.assertEqual(side_scores([]), SideScores(0, 0))
        self.assertEqual(side_scores([tf("M5", 3, 0, insufficient=True)]), SideScores(0, 0))

    def test_weights_shift_the_balance_toward_the_weighted_timeframe(self):
        tfs = [tf("H4", 5, 0), tf("M5", 0, 5)]
        slow = side_scores(tfs, {"H4": 3.0, "M5": 1.0})
        fast = side_scores(tfs, {"H4": 1.0, "M5": 3.0})
        self.assertEqual(slow.leader, "CALL")
        self.assertEqual(fast.leader, "PUT")
        self.assertEqual(slow.difference, fast.difference)

    def test_zero_weight_timeframes_are_dropped_not_divided_by(self):
        s = side_scores([tf("M5", 5, 0), tf("H4", 0, 5)], {"H4": 0.0})
        self.assertEqual((s.call, s.put), (100, 0))

    def test_a_near_tie_is_visible_as_a_small_difference(self):
        """CALL 78 / PUT 70 is the setup the separation gate exists to
        reject, and the old single score could not represent it at all."""
        s = side_scores([tf("M5", 3, 2), tf("M15", 3, 2), tf("H1", 2, 3), tf("H4", 3, 2)])
        self.assertLess(s.difference, 20)
        self.assertNotEqual(s.leader, "NO_TRADE")


class ConflictTests(unittest.TestCase):
    def test_conflict_is_zero_when_voters_agree(self):
        self.assertEqual(tf("M5", 4, 0).conflict, 0.0)

    def test_conflict_is_one_on_an_even_split(self):
        self.assertEqual(tf("M5", 2, 2).conflict, 1.0)

    def test_silence_is_not_conflict(self):
        self.assertEqual(tf("M5", 0, 0).conflict, 0.0)
        self.assertEqual(tf("M5", 0, 0).voters, 0)


if __name__ == "__main__":
    unittest.main()
