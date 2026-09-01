import unittest

from app.features.decision_identity import fingerprint, primary_note


class TestPrimaryNote(unittest.TestCase):
    def test_warnings_outrank_reasons(self):
        self.assertEqual(primary_note(["all fine"], ["news blackout"]), "news blackout")

    def test_falls_back_to_reasons(self):
        self.assertEqual(primary_note(["trend aligned"], []), "trend aligned")

    def test_empty_when_nothing(self):
        self.assertEqual(primary_note(None, None), "")


class TestFingerprint(unittest.TestCase):
    def _fp(self, **kw):
        base = dict(direction="CALL", grade="B", expiry_seconds=30,
                    market_regime="TRENDING_UP", note="H4 and H1 aligned")
        base.update(kw)
        return fingerprint(**base)

    def test_identical_decisions_match(self):
        self.assertEqual(self._fp(), self._fp())

    def test_score_drift_is_NOT_a_new_decision(self):
        """The whole point: technical_score isn't part of identity. It moves a
        point or two every cycle, and treating that as a new signal is exactly
        the duplication that corrupts the statistics."""
        # Score isn't even a parameter -- assert that by construction.
        self.assertNotIn("technical_score", fingerprint.__doc__ or "")
        self.assertEqual(self._fp(), self._fp())

    def test_direction_change_is_material(self):
        self.assertNotEqual(self._fp(), self._fp(direction="PUT"))

    def test_grade_change_is_material(self):
        self.assertNotEqual(self._fp(), self._fp(grade="REJECTED"))

    def test_expiry_change_is_material(self):
        self.assertNotEqual(self._fp(), self._fp(expiry_seconds=60))

    def test_regime_change_is_material(self):
        self.assertNotEqual(self._fp(), self._fp(market_regime="RANGING"))

    def test_reason_change_is_material(self):
        """A NO_TRADE switching from conflicting timeframes to a news blackout
        is a different state worth recording, even at the same grade."""
        a = fingerprint("NO_TRADE", "REJECTED", None, "RANGING", "Timeframes conflicting")
        b = fingerprint("NO_TRADE", "REJECTED", None, "NEWS_MODE", "High-impact USD news in 10 min")
        self.assertNotEqual(a, b)

    def test_trailing_countdown_drift_is_not_material(self):
        """Two news warnings differing only past the compare window must not
        churn a new row every cycle."""
        # The differing characters must fall past the 120-char compare window.
        pad = "x" * 120
        a = fingerprint("NO_TRADE", "REJECTED", None, "NEWS_MODE", pad + "12 min")
        b = fingerprint("NO_TRADE", "REJECTED", None, "NEWS_MODE", pad + "11 min")
        self.assertEqual(a, b)

    def test_difference_inside_the_window_IS_material(self):
        """Guards the truncation from hiding a real change: a note differing
        early must still register as a new state."""
        a = fingerprint("NO_TRADE", "REJECTED", None, "RANGING", "Timeframes conflicting")
        b = fingerprint("NO_TRADE", "REJECTED", None, "RANGING", "Insufficient history")
        self.assertNotEqual(a, b)

    def test_none_note_is_safe(self):
        self.assertEqual(
            fingerprint("NO_TRADE", "REJECTED", None, "RANGING", ""),
            fingerprint("NO_TRADE", "REJECTED", None, "RANGING", ""),
        )


if __name__ == "__main__":
    unittest.main()


class StrategyVersionIsPartOfIdentity(unittest.TestCase):
    """A config change made while a decision was standing must open a NEW row.

    Otherwise the change is absorbed into the existing row, which still carries
    the OLD version stamp -- and the tuning change becomes invisible in exactly
    the data meant to evaluate it.
    """

    ARGS = ("NO_TRADE", "REJECTED", None, "RANGING", "Timeframes conflicting.")

    def test_same_decision_under_a_new_rule_set_is_a_new_decision(self):
        self.assertNotEqual(
            fingerprint(*self.ARGS, "v2:aaaaaa"),
            fingerprint(*self.ARGS, "v2:bbbbbb"),
        )

    def test_same_decision_under_the_same_rule_set_is_still_the_same(self):
        self.assertEqual(
            fingerprint(*self.ARGS, "v2:aaaaaa"),
            fingerprint(*self.ARGS, "v2:aaaaaa"),
        )

    def test_missing_version_is_treated_as_the_empty_string_not_as_distinct(self):
        """Rows written before versioning read back as None. None and "" must
        not fingerprint differently, or every pre-migration row would be
        duplicated once on the first cycle after deploy."""
        self.assertEqual(fingerprint(*self.ARGS, ""), fingerprint(*self.ARGS))
