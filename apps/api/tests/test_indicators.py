import unittest

from app.features import indicators as ind


class TestEma(unittest.TestCase):
    def test_none_when_not_enough_data(self):
        self.assertIsNone(ind.ema_latest([1.0, 2.0, 3.0], period=5))

    def test_ema_matches_sma_seed_at_exact_period(self):
        values = [1.0, 2.0, 3.0, 4.0, 5.0]
        self.assertAlmostEqual(ind.ema_latest(values, period=5), 3.0)

    def test_ema_smooths_forward(self):
        values = [10.0] * 20 + [20.0]
        # after one bar moving from a flat 10 to 20, EMA should move partway
        # toward 20 but not reach it.
        latest = ind.ema_latest(values, period=10)
        self.assertGreater(latest, 10.0)
        self.assertLess(latest, 20.0)

    def test_ema_slope_positive_for_uptrend(self):
        values = [100 + i for i in range(30)]
        slope = ind.ema_slope(values, period=10, lookback=3)
        self.assertIsNotNone(slope)
        self.assertGreater(slope, 0)


class TestRsi(unittest.TestCase):
    def test_none_when_not_enough_data(self):
        self.assertIsNone(ind.rsi_latest([1.0, 2.0], period=14))

    def test_all_gains_gives_rsi_100(self):
        values = [float(i) for i in range(1, 20)]  # strictly increasing
        self.assertAlmostEqual(ind.rsi_latest(values, period=14), 100.0)

    def test_all_losses_gives_rsi_0(self):
        values = [float(i) for i in range(20, 1, -1)]  # strictly decreasing
        self.assertAlmostEqual(ind.rsi_latest(values, period=14), 0.0)

    def test_flat_series_gives_rsi_100_by_convention(self):
        # no losses at all -> avg_loss == 0 -> RSI defined as 100
        values = [50.0] * 20
        self.assertAlmostEqual(ind.rsi_latest(values, period=14), 100.0)


class TestMacd(unittest.TestCase):
    def test_none_when_not_enough_data(self):
        self.assertIsNone(ind.macd_latest([float(i) for i in range(10)]))

    def test_returns_result_with_enough_data(self):
        values = [100 + i * 0.5 for i in range(60)]
        result = ind.macd_latest(values)
        self.assertIsNotNone(result)
        # steady uptrend -> fast EMA above slow EMA -> positive MACD
        self.assertGreater(result.macd, 0)


class TestAtr(unittest.TestCase):
    def _candle(self, high, low, close):
        return {"high": high, "low": low, "close": close}

    def test_none_when_not_enough_data(self):
        candles = [self._candle(10, 9, 9.5) for _ in range(5)]
        self.assertIsNone(ind.atr_latest(candles, period=14))

    def test_constant_range_gives_that_range(self):
        # every candle has a true range of exactly 2 (high-low=2, no gaps)
        candles = [self._candle(101.0, 99.0, 100.0) for _ in range(20)]
        atr = ind.atr_latest(candles, period=14)
        self.assertAlmostEqual(atr, 2.0, places=5)

    def test_percentile_none_with_too_little_history(self):
        candles = [self._candle(101.0, 99.0, 100.0) for _ in range(16)]
        self.assertIsNone(ind.atr_percentile(candles, period=14))

    def test_percentile_near_100_for_a_new_high(self):
        candles = [self._candle(100.5, 99.5, 100.0) for _ in range(40)]
        # widen the range sharply on the last candle only
        candles.append(self._candle(120.0, 80.0, 100.0))
        pct = ind.atr_percentile(candles, period=14)
        self.assertIsNotNone(pct)
        # Strictly the highest observation; the midpoint tie convention puts
        # a unique maximum just under 100, not exactly at it.
        self.assertGreater(pct, 95.0)

    def test_flat_volatility_reads_as_ordinary_not_extreme(self):
        # Every candle has an identical true range. This must NOT read as
        # the 100th percentile -- steady volatility is ordinary, and the
        # regime engine stands down on HIGH_VOLATILITY.
        candles = [self._candle(101.0, 99.0, 100.0) for _ in range(40)]
        self.assertEqual(ind.atr_percentile(candles, period=14), 50.0)


class TestBollinger(unittest.TestCase):
    def test_none_when_not_enough_data(self):
        self.assertIsNone(ind.bollinger_latest([1.0, 2.0, 3.0], period=20))

    def test_flat_series_has_zero_width(self):
        result = ind.bollinger_latest([50.0] * 20, period=20)
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result.width_pct, 0.0)
        self.assertAlmostEqual(result.mid, 50.0)


if __name__ == "__main__":
    unittest.main()
