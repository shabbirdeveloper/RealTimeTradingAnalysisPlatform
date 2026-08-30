import unittest

from app.features.outcome import outcome


class TestOutcome(unittest.TestCase):
    def test_call_wins_when_price_rises(self):
        self.assertEqual(outcome("CALL", 100.0, 101.0), "WON")

    def test_call_loses_when_price_falls(self):
        self.assertEqual(outcome("CALL", 100.0, 99.0), "LOST")

    def test_put_wins_when_price_falls(self):
        self.assertEqual(outcome("PUT", 100.0, 99.0), "WON")

    def test_put_loses_when_price_rises(self):
        self.assertEqual(outcome("PUT", 100.0, 101.0), "LOST")

    def test_equal_price_is_a_draw_both_directions(self):
        self.assertEqual(outcome("CALL", 100.0, 100.0), "DRAW")
        self.assertEqual(outcome("PUT", 100.0, 100.0), "DRAW")

    def test_tiny_moves_still_decide(self):
        """No epsilon: a binary settles on the quoted price, however small
        the move. Introducing a tolerance here would silently reclassify
        real wins and losses as draws."""
        self.assertEqual(outcome("CALL", 100.0, 100.00001), "WON")
        self.assertEqual(outcome("PUT", 100.0, 100.00001), "LOST")

    def test_no_trade_is_rejected_not_silently_scored(self):
        """A NO_TRADE has no outcome. Returning something plausible would let
        non-trades leak into accuracy statistics."""
        with self.assertRaises(ValueError):
            outcome("NO_TRADE", 100.0, 101.0)

    def test_symmetry_call_and_put_never_both_win(self):
        for entry, close in ((100.0, 103.5), (100.0, 96.5), (2410.0, 2410.75)):
            results = {outcome("CALL", entry, close), outcome("PUT", entry, close)}
            self.assertEqual(results, {"WON", "LOST"}, f"{entry}->{close}")
