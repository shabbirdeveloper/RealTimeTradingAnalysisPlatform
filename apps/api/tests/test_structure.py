import unittest
from datetime import datetime, timedelta, timezone

from app.features import structure as struct


def make_candles(prices: list[tuple[float, float, float, float]], start=None, step_minutes=5):
    """prices: list of (open, high, low, close). Returns candles oldest-first
    with real, evenly-spaced UTC timestamps."""
    start = start or datetime(2026, 8, 31, 0, 0, tzinfo=timezone.utc)  # a Monday
    candles = []
    for i, (o, h, l, c) in enumerate(prices):
        candles.append({
            "open": o, "high": h, "low": l, "close": c,
            "open_time": start + timedelta(minutes=step_minutes * i),
        })
    return candles


class TestFindSwings(unittest.TestCase):
    def test_empty_with_too_few_candles(self):
        candles = make_candles([(1, 1, 1, 1)] * 3)
        self.assertEqual(struct.find_swings(candles, window=2), [])

    def test_detects_a_clean_swing_high(self):
        # a single peak in the middle, everything else flat/lower
        highs = [1, 1, 1, 5, 1, 1, 1]
        candles = make_candles([(h, h, h - 0.5, h) for h in highs])
        swings = struct.find_swings(candles, window=2)
        swing_highs = [s for s in swings if s.kind == "high"]
        self.assertEqual(len(swing_highs), 1)
        self.assertEqual(swing_highs[0].index, 3)
        self.assertEqual(swing_highs[0].price, 5)


class TestClassifyStructure(unittest.TestCase):
    def test_insufficient_data_with_no_swings(self):
        candles = make_candles([(1, 1, 1, 1)] * 3)
        reading = struct.classify_structure(candles)
        self.assertIsNone(reading.sequence)

    def test_higher_high_higher_low_sequence(self):
        # Two clean up-swings: peak at 5 then a bigger peak at 8, with
        # troughs at 1 then a higher trough at 2.
        pattern = [
            2, 2, 5, 2, 2,   # first swing high at idx 2 (price 5)
            2, 2, 1, 2, 2,   # first swing low at idx 7 (price 1) -- wait need higher low later
        ]
        # Build explicitly instead of via a shared pattern for clarity.
        vals = [3, 3, 5, 3, 3, 3, 3, 1, 3, 3, 3, 3, 8, 3, 3, 3, 3, 2, 3, 3]
        candles = make_candles([(v, v, v, v) for v in vals])
        reading = struct.classify_structure(candles, window=2)
        self.assertEqual(reading.sequence, "HH_HL")
        self.assertEqual(reading.resistance, 8)
        self.assertEqual(reading.support, 2)
        # last close (3) sits inside the most recent swing range (2-8) --
        # no break of structure yet, which is the honest reading here.
        self.assertFalse(reading.bos)


class TestSessionForTime(unittest.TestCase):
    def test_asian_session(self):
        self.assertEqual(struct.session_for_time(datetime(2026, 8, 31, 3, 0, tzinfo=timezone.utc)), "ASIAN")

    def test_london_session(self):
        self.assertEqual(struct.session_for_time(datetime(2026, 8, 31, 9, 0, tzinfo=timezone.utc)), "LONDON")

    def test_overlap_session(self):
        self.assertEqual(struct.session_for_time(datetime(2026, 8, 31, 13, 0, tzinfo=timezone.utc)), "LONDON_NY_OVERLAP")

    def test_new_york_session(self):
        self.assertEqual(struct.session_for_time(datetime(2026, 8, 31, 18, 0, tzinfo=timezone.utc)), "NEW_YORK")


class TestSessionRanges(unittest.TestCase):
    def test_ranges_computed_from_real_candles(self):
        start = datetime(2026, 8, 31, 0, 0, tzinfo=timezone.utc)
        candles = []
        # Asian session (0-7 UTC): high 10, low 9
        for h in range(0, 7):
            candles.append({"high": 10.0, "low": 9.0, "close": 9.5, "open_time": start.replace(hour=h)})
        # London session (7-12 UTC): high 12, low 11
        for h in range(7, 12):
            candles.append({"high": 12.0, "low": 11.0, "close": 11.5, "open_time": start.replace(hour=h)})
        now = start.replace(hour=12)
        ranges = struct.session_ranges(candles, now)
        self.assertEqual(ranges.asian_high, 10.0)
        self.assertEqual(ranges.asian_low, 9.0)
        self.assertEqual(ranges.london_high, 12.0)
        self.assertEqual(ranges.london_low, 11.0)

    def test_none_when_no_candles_in_range(self):
        now = datetime(2026, 8, 31, 12, 0, tzinfo=timezone.utc)
        ranges = struct.session_ranges([], now)
        self.assertIsNone(ranges.asian_high)
        self.assertIsNone(ranges.london_high)


if __name__ == "__main__":
    unittest.main()
