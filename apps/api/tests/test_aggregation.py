import unittest
from datetime import datetime, timezone
from decimal import Decimal

from app.aggregation import (
    AggregationError,
    Candle,
    Timeframe,
    _bucket_start,
    aggregate_candles,
)


def dt(h, m, day=1):
    return datetime(2026, 8, day, h, m, tzinfo=timezone.utc)


def m5(hour, minute, o, h, l, c, v=None):
    return Candle(
        open_time=dt(hour, minute),
        open=Decimal(str(o)),
        high=Decimal(str(h)),
        low=Decimal(str(l)),
        close=Decimal(str(c)),
        volume=Decimal(str(v)) if v is not None else None,
    )


class TestBucketAlignment(unittest.TestCase):
    def test_h1_floors_to_top_of_hour(self):
        self.assertEqual(_bucket_start(dt(9, 47), Timeframe.H1), dt(9, 0))

    def test_h4_floors_to_4hour_boundary(self):
        self.assertEqual(_bucket_start(dt(13, 20), Timeframe.H4), dt(12, 0))
        self.assertEqual(_bucket_start(dt(0, 5), Timeframe.H4), dt(0, 0))
        self.assertEqual(_bucket_start(dt(23, 59), Timeframe.H4), dt(20, 0))

    def test_m15_floors_to_quarter_hour(self):
        self.assertEqual(_bucket_start(dt(9, 37), Timeframe.M15), dt(9, 30))


class TestAggregateM5ToH1(unittest.TestCase):
    def test_complete_12_bars_produce_one_correct_h1_bar(self):
        bars = [
            m5(9, 0, 100, 101, 99, 100.5),
            m5(9, 5, 100.5, 102, 100, 101.5),
            m5(9, 10, 101.5, 103, 101, 102.8, v=10),
            m5(9, 15, 102.8, 103.5, 102, 103, v=5),
            m5(9, 20, 103, 104, 102.5, 103.2),
            m5(9, 25, 103.2, 103.4, 101.9, 102),
            m5(9, 30, 102, 102.5, 100.8, 101),
            m5(9, 35, 101, 101.9, 100.5, 101.5),
            m5(9, 40, 101.5, 105, 101.3, 104.9),
            m5(9, 45, 104.9, 105.2, 104, 104.5),
            m5(9, 50, 104.5, 104.8, 103.9, 104.1),
            m5(9, 55, 104.1, 104.3, 99.5, 100.2, v=7),
        ]
        result = aggregate_candles(bars, Timeframe.M5, Timeframe.H1)
        self.assertEqual(len(result), 1)
        h1 = result[0]
        self.assertEqual(h1.open_time, dt(9, 0))
        self.assertEqual(h1.open, Decimal("100"))       # first bar's open
        self.assertEqual(h1.close, Decimal("100.2"))     # last bar's close
        self.assertEqual(h1.high, Decimal("105.2"))       # max of all highs
        self.assertEqual(h1.low, Decimal("99"))            # min of all lows (09:00 bar)
        self.assertEqual(h1.volume, Decimal("22"))         # 10 + 5 + 7

    def test_incomplete_bucket_without_now_is_dropped(self):
        bars = [m5(9, i * 5, 100, 101, 99, 100) for i in range(8)]  # only 8 of 12
        result = aggregate_candles(bars, Timeframe.M5, Timeframe.H1)
        self.assertEqual(result, [])

    def test_incomplete_bucket_emitted_once_wallclock_has_passed(self):
        bars = [m5(9, i * 5, 100 + i, 101 + i, 99 + i, 100 + i) for i in range(8)]
        result = aggregate_candles(bars, Timeframe.M5, Timeframe.H1, now=dt(11, 0))
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].open_time, dt(9, 0))
        self.assertEqual(result[0].close, Decimal("107"))  # last (8th, i=7) bar's close

    def test_still_forming_bucket_not_emitted_even_with_now(self):
        bars = [m5(9, i * 5, 100, 101, 99, 100) for i in range(8)]
        # now is inside the bucket (09:00-10:00), bucket end hasn't arrived yet
        result = aggregate_candles(bars, Timeframe.M5, Timeframe.H1, now=dt(9, 40))
        self.assertEqual(result, [])

    def test_two_separate_hours_both_complete(self):
        hour1 = [m5(9, i * 5, 100, 101, 99, 100) for i in range(12)]
        hour2 = [m5(10, i * 5, 200, 201, 199, 200) for i in range(12)]
        result = aggregate_candles(hour1 + hour2, Timeframe.M5, Timeframe.H1)
        self.assertEqual([c.open_time for c in result], [dt(9, 0), dt(10, 0)])


class TestAggregateM5ToM15(unittest.TestCase):
    def test_three_bars_make_one_m15_bar(self):
        bars = [
            m5(9, 0, 100, 102, 99, 101),
            m5(9, 5, 101, 103, 100.5, 102),
            m5(9, 10, 102, 102.5, 101, 101.8),
        ]
        result = aggregate_candles(bars, Timeframe.M5, Timeframe.M15)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].open_time, dt(9, 0))
        self.assertEqual(result[0].open, Decimal("100"))
        self.assertEqual(result[0].close, Decimal("101.8"))
        self.assertEqual(result[0].high, Decimal("103"))
        self.assertEqual(result[0].low, Decimal("99"))


class TestMisuse(unittest.TestCase):
    def test_same_source_and_target_raises(self):
        with self.assertRaises(AggregationError):
            aggregate_candles([], Timeframe.M5, Timeframe.M5)

    def test_non_multiple_timeframes_raise(self):
        # M15 -> M5 (target smaller than source) must raise, not silently
        # "aggregate downward".
        with self.assertRaises(AggregationError):
            aggregate_candles([], Timeframe.M15, Timeframe.M5)

    def test_naive_datetime_rejected(self):
        with self.assertRaises(AggregationError):
            Candle(
                open_time=datetime(2026, 8, 1, 9, 0),  # no tzinfo
                open=Decimal("1"),
                high=Decimal("1"),
                low=Decimal("1"),
                close=Decimal("1"),
            )


if __name__ == "__main__":
    unittest.main()
