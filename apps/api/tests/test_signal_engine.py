import unittest
from datetime import datetime, timedelta, timezone

from app.features.signal_engine import build_signal


def make_candles(n: int, start_price: float, drift_per_bar: float, step_minutes: int, start=None, noise=0.0):
    """A clean, mostly-monotonic synthetic OHLC series for engine-level
    tests -- NOT used anywhere in the app itself, only here to exercise
    build_signal() against inputs shaped like real stored candles."""
    start = start or datetime(2026, 8, 24, 0, 0, tzinfo=timezone.utc)  # a Monday, well before "now"
    candles = []
    price = start_price
    for i in range(n):
        o = price
        c = price + drift_per_bar
        h = max(o, c) + noise
        l = min(o, c) - noise
        candles.append({
            "open": o, "high": h, "low": l, "close": c,
            "open_time": start + timedelta(minutes=step_minutes * i),
        })
        price = c
    return candles


class TestBuildSignal(unittest.TestCase):
    def test_no_trade_when_insufficient_history(self):
        candles_by_tf = {
            "H4": make_candles(5, 2400, 1, 240),
            "H1": make_candles(5, 2400, 1, 60),
            "M15": make_candles(5, 2400, 1, 15),
            "M5": make_candles(5, 2400, 1, 5),
        }
        decision = build_signal("XAUUSD", candles_by_tf, now=datetime.now(timezone.utc))
        self.assertEqual(decision.direction, "NO_TRADE")
        self.assertEqual(decision.grade, "REJECTED")
        self.assertTrue(any("Not enough real candle history" in w for w in decision.warnings))

    def test_never_returns_a_grade_above_b(self):
        # Even with a very clean, strongly trending synthetic series (which
        # should score well), the grade must never exceed B -- there is no
        # calibrated ML confidence to justify A/A+/A++ (spec section 10).
        candles_by_tf = {
            "H4": make_candles(250, 2000, 3.0, 240),
            "H1": make_candles(250, 2000, 1.0, 60),
            "M15": make_candles(250, 2000, 0.4, 15),
            "M5": make_candles(250, 2000, 0.15, 5),
        }
        decision = build_signal("XAUUSD", candles_by_tf, now=datetime.now(timezone.utc))
        self.assertIn(decision.grade, ("B", "REJECTED"))
        for c in decision.candidates:
            self.assertIn(c.grade, ("B", "REJECTED"))

    def test_strong_uptrend_produces_call_or_no_trade_never_put(self):
        candles_by_tf = {
            "H4": make_candles(250, 2000, 3.0, 240),
            "H1": make_candles(250, 2000, 1.0, 60),
            "M15": make_candles(250, 2000, 0.4, 15),
            "M5": make_candles(250, 2000, 0.15, 5),
        }
        decision = build_signal("XAUUSD", candles_by_tf, now=datetime.now(timezone.utc))
        self.assertIn(decision.direction, ("CALL", "NO_TRADE"))

    def test_flat_market_produces_no_trade(self):
        candles_by_tf = {
            "H4": make_candles(250, 2000, 0.0, 240, noise=0.5),
            "H1": make_candles(250, 2000, 0.0, 60, noise=0.5),
            "M15": make_candles(250, 2000, 0.0, 15, noise=0.5),
            "M5": make_candles(250, 2000, 0.0, 5, noise=0.5),
        }
        decision = build_signal("EURUSD", candles_by_tf, now=datetime.now(timezone.utc))
        self.assertEqual(decision.direction, "NO_TRADE")

    def test_never_fabricates_calibrated_confidence(self):
        candles_by_tf = {
            "H4": make_candles(250, 2000, 3.0, 240),
            "H1": make_candles(250, 2000, 1.0, 60),
            "M15": make_candles(250, 2000, 0.4, 15),
            "M5": make_candles(250, 2000, 0.15, 5),
        }
        decision = build_signal("XAUUSD", candles_by_tf, now=datetime.now(timezone.utc))
        self.assertTrue(any("Meta trade/no-trade model not available" in w for w in decision.warnings))


if __name__ == "__main__":
    unittest.main()


class TestNewsProtection(unittest.TestCase):
    """Spec section 8: a high-impact news window pauses signals outright."""

    def _trending_history(self):
        return {
            "H4": make_candles(250, 2000, 3.0, 240),
            "H1": make_candles(250, 2000, 1.0, 60),
            "M15": make_candles(250, 2000, 0.4, 15),
            "M5": make_candles(250, 2000, 0.2, 5),
        }

    def test_warns_loudly_when_no_calendar_is_configured(self):
        decision = build_signal("XAUUSD", self._trending_history(), now=datetime.now(timezone.utc))
        self.assertTrue(
            any("NOT being screened" in w for w in decision.warnings),
            "an unconfigured calendar must be stated, not silently treated as all-clear",
        )

    def test_does_not_warn_when_a_calendar_is_configured_and_quiet(self):
        decision = build_signal(
            "XAUUSD", self._trending_history(), now=datetime.now(timezone.utc),
            economic_events=[], calendar_available=True,
        )
        self.assertFalse(any("NOT being screened" in w for w in decision.warnings))

    def test_high_impact_news_pauses_signals(self):
        from app.news.blackout import EconomicEvent

        now = datetime.now(timezone.utc)
        event = EconomicEvent("US CPI", "USD", now + timedelta(minutes=10), "HIGH")
        decision = build_signal(
            "XAUUSD", self._trending_history(), now=now,
            economic_events=[event], calendar_available=True,
        )
        # The same history produces a CALL with no news -- so this NO_TRADE
        # is caused by the blackout, not by weak conditions.
        self.assertEqual(decision.direction, "NO_TRADE")
        self.assertEqual(decision.market_regime, "NEWS_MODE")
        self.assertIsNone(decision.expiry_minutes)
        self.assertTrue(any("US CPI" in w for w in decision.warnings))

    def test_same_history_trades_when_the_news_is_far_away(self):
        from app.news.blackout import EconomicEvent

        now = datetime.now(timezone.utc)
        far = EconomicEvent("US CPI", "USD", now + timedelta(hours=6), "HIGH")
        decision = build_signal(
            "XAUUSD", self._trending_history(), now=now,
            economic_events=[far], calendar_available=True,
        )
        self.assertNotEqual(decision.market_regime, "NEWS_MODE")

    def test_irrelevant_currency_news_does_not_pause(self):
        from app.news.blackout import EconomicEvent

        now = datetime.now(timezone.utc)
        # EUR news must not pause gold.
        event = EconomicEvent("ECB Rate Decision", "EUR", now + timedelta(minutes=5), "HIGH")
        decision = build_signal(
            "XAUUSD", self._trending_history(), now=now,
            economic_events=[event], calendar_available=True,
        )
        self.assertNotEqual(decision.market_regime, "NEWS_MODE")

    def test_timeframes_still_reported_during_a_pause(self):
        from app.news.blackout import EconomicEvent

        now = datetime.now(timezone.utc)
        event = EconomicEvent("NFP", "USD", now, "HIGH")
        decision = build_signal(
            "XAUUSD", self._trending_history(), now=now,
            economic_events=[event], calendar_available=True,
        )
        self.assertEqual(len(decision.timeframes), 4)


class TestSyntheticInstrumentGuard(unittest.TestCase):
    """The engine must refuse broker-synthetic instruments outright rather
    than producing a confident-looking signal about a price series the user
    isn't actually trading. See app/instruments.py."""

    def _history(self):
        return {
            "H4": make_candles(250, 2000, 3.0, 240),
            "H1": make_candles(250, 2000, 1.0, 60),
            "M15": make_candles(250, 2000, 0.4, 15),
            "M5": make_candles(250, 2000, 0.2, 5),
        }

    def test_otc_symbol_is_refused(self):
        from app.instruments import SyntheticInstrumentError

        with self.assertRaises(SyntheticInstrumentError):
            build_signal("EURUSD-OTC", self._history(), now=datetime.now(timezone.utc))

    def test_real_symbol_still_works(self):
        decision = build_signal("EURUSD", self._history(), now=datetime.now(timezone.utc))
        self.assertIn(decision.direction, ("CALL", "PUT", "NO_TRADE"))
