import unittest
from datetime import datetime, timedelta, timezone

from app.features.signal_engine import build_signal


def make_candles(n: int, start_price: float, drift_per_bar: float, step_minutes: int,
                 start=None, noise=0.0, ending_at=None):
    """A clean, mostly-monotonic synthetic OHLC series for engine-level
    tests -- NOT used anywhere in the app itself, only here to exercise
    build_signal() against inputs shaped like real stored candles.

    Anchored so the series ENDS at `ending_at` (default: now), because the
    engine now refuses to analyse stale data. A fixture pinned to a fixed
    past date would be permanently stale and every test would trivially
    return NO_TRADE -- which is exactly what happened when the staleness
    gate was first added.
    """
    ending_at = ending_at or datetime.now(timezone.utc)
    if start is None:
        # Last bar closes exactly at `ending_at`.
        start = ending_at - timedelta(minutes=step_minutes * n)
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
        self.assertIsNone(decision.expiry_seconds)
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

    def test_otc_instrument_priced_by_a_forex_feed_is_refused(self):
        """The dangerous case: real interbank EUR/USD analysed and shipped as
        a graded signal for Quotex's EUR/USD OTC, which is a different series
        entirely."""
        from app.instruments import FeedDescriptor, FeedKind, FeedProvenanceError

        with self.assertRaises(FeedProvenanceError):
            build_signal(
                "EURUSD_OTC", self._history(), now=datetime.now(timezone.utc),
                feed=FeedDescriptor("twelve_data", FeedKind.PUBLIC_MARKET),
            )

    def test_otc_instrument_without_stated_provenance_is_refused(self):
        from app.instruments import FeedProvenanceError

        with self.assertRaises(FeedProvenanceError):
            build_signal("EURUSD_OTC", self._history(), now=datetime.now(timezone.utc))

    def test_unregistered_otc_spelling_is_refused(self):
        from app.instruments import UnknownInstrumentError

        with self.assertRaises(UnknownInstrumentError):
            build_signal("EURUSD-OTC", self._history(), now=datetime.now(timezone.utc))

    def test_otc_instrument_with_its_own_broker_feed_is_analysed(self):
        """The point of the provenance rule: OTC becomes legitimate the
        moment genuine OTC prices are what is flowing in."""
        from app.instruments import FeedDescriptor, FeedKind

        decision = build_signal(
            "EURUSD_OTC", self._history(), now=datetime.now(timezone.utc),
            feed=FeedDescriptor("quotex_otc", FeedKind.BROKER_OTC, broker="QUOTEX"),
        )
        self.assertIn(decision.direction, ("CALL", "PUT", "NO_TRADE"))
        self.assertEqual(decision.market_type, "BROKER_OTC")
        self.assertEqual(decision.data_source, "quotex_otc")

    def test_real_symbol_still_works(self):
        decision = build_signal("EURUSD", self._history(), now=datetime.now(timezone.utc))
        self.assertIn(decision.direction, ("CALL", "PUT", "NO_TRADE"))


class TestStalenessGate(unittest.TestCase):
    """Spec section 42: signal generation must pause on stale data.

    This is the gate that stops the engine describing a market that no
    longer exists -- with an entry_price that is no longer tradeable.
    """

    def _history(self, ending_at):
        return {
            "H4": make_candles(250, 2000, 3.0, 240, ending_at=ending_at),
            "H1": make_candles(250, 2000, 1.0, 60, ending_at=ending_at),
            "M15": make_candles(250, 2000, 0.4, 15, ending_at=ending_at),
            "M5": make_candles(250, 2000, 0.2, 5, ending_at=ending_at),
        }

    def test_fresh_data_still_produces_a_signal(self):
        """Guards the tests below from passing because the fixture is broken."""
        now = datetime.now(timezone.utc)
        decision = build_signal("XAUUSD", self._history(now), now=now)
        self.assertNotEqual(decision.direction, "NO_TRADE")
        self.assertFalse(any("stale" in w.lower() for w in decision.warnings))

    def test_stale_data_blocks_the_signal(self):
        now = datetime.now(timezone.utc)
        # Same history, but evaluated three hours later -- a stalled collector.
        decision = build_signal("XAUUSD", self._history(now), now=now + timedelta(hours=3))
        self.assertEqual(decision.direction, "NO_TRADE")
        self.assertEqual(decision.grade, "REJECTED")
        self.assertIsNone(decision.expiry_seconds)
        self.assertTrue(any("stale" in w.lower() for w in decision.warnings))

    def test_age_is_measured_from_candle_close_not_open(self):
        """A bar that opened 6 minutes ago closed 1 minute ago and is fresh.
        Measuring from open_time would reject perfectly good data."""
        now = datetime.now(timezone.utc)
        history = self._history(now - timedelta(minutes=1))  # last close 1 min ago
        decision = build_signal("XAUUSD", history, now=now)
        self.assertFalse(any("stale" in w.lower() for w in decision.warnings))

    def test_boundary_just_inside_the_limit_is_allowed(self):
        now = datetime.now(timezone.utc)
        history = self._history(now - timedelta(minutes=14))
        decision = build_signal("XAUUSD", history, now=now, max_candle_age_minutes=15)
        self.assertFalse(any("stale" in w.lower() for w in decision.warnings))

    def test_boundary_just_outside_the_limit_is_blocked(self):
        now = datetime.now(timezone.utc)
        history = self._history(now - timedelta(minutes=16))
        decision = build_signal("XAUUSD", history, now=now, max_candle_age_minutes=15)
        self.assertTrue(any("stale" in w.lower() for w in decision.warnings))

    def test_threshold_is_configurable(self):
        now = datetime.now(timezone.utc)
        history = self._history(now - timedelta(minutes=45))
        self.assertTrue(any("stale" in w.lower()
                            for w in build_signal("XAUUSD", history, now=now).warnings))
        self.assertFalse(any("stale" in w.lower()
                             for w in build_signal("XAUUSD", history, now=now,
                                                   max_candle_age_minutes=90).warnings))

    def test_empty_history_is_reported_not_crashed(self):
        now = datetime.now(timezone.utc)
        history = self._history(now)
        history["M5"] = []
        decision = build_signal("XAUUSD", history, now=now)
        self.assertEqual(decision.direction, "NO_TRADE")

    def test_stale_decision_carries_no_tradeable_entry_expiry(self):
        """The dangerous failure would be emitting a graded signal with a
        stale entry price. Assert nothing actionable escapes."""
        now = datetime.now(timezone.utc)
        decision = build_signal("XAUUSD", self._history(now), now=now + timedelta(hours=6))
        self.assertIsNone(decision.expiry_seconds)
        self.assertEqual(decision.technical_score, 0)
        self.assertEqual(decision.candidates, [])
        self.assertIsNone(decision.rejected_opportunity_direction)


class DecisionChecksExplainThemselves(unittest.TestCase):
    """Spec Phase 26. A NO_TRADE carrying one sentence says what happened but
    not how close it came or which gate was responsible — which is what
    someone staring at an unchanging card actually wants to know."""

    def _conflicting(self, now):
        return {
            "H4": make_candles(300, 2400, 3.0, 240, ending_at=now),
            "H1": make_candles(300, 2400, 1.0, 60, ending_at=now),
            "M15": make_candles(300, 2400, -0.6, 15, ending_at=now),
            "M5": make_candles(300, 2400, -0.3, 5, ending_at=now),
        }

    def _trending(self, now):
        return {tf: make_candles(300, 2400, drift, step, ending_at=now)
                for tf, drift, step in
                (("H4", 24.0, 240), ("H1", 6.0, 60), ("M15", 1.5, 15), ("M5", 0.5, 5))}

    def test_every_decision_records_its_gates(self):
        now = datetime.now(timezone.utc)
        for history in (self._conflicting(now), self._trending(now)):
            decision = build_signal("XAUUSD", history, now=now)
            self.assertTrue(decision.checks, "no checks recorded")
            names = [c.name for c in decision.checks]
            self.assertIn("Data freshness", names)
            self.assertIn("Multi-timeframe agreement", names)

    def test_the_failing_gate_is_identifiable(self):
        now = datetime.now(timezone.utc)
        decision = build_signal("XAUUSD", self._conflicting(now), now=now)
        self.assertEqual(decision.direction, "NO_TRADE")
        failed = [c for c in decision.checks if not c.passed]
        self.assertEqual(len(failed), 1, "exactly one gate should stop a decision")
        self.assertEqual(failed[0].name, "Multi-timeframe agreement")

    def test_the_agreement_gate_shows_the_shortfall_numerically(self):
        """'Conflicting' is a verdict; '2 of 4, needs 3' is information."""
        now = datetime.now(timezone.utc)
        decision = build_signal("XAUUSD", self._conflicting(now), now=now)
        gate = next(c for c in decision.checks if c.name == "Multi-timeframe agreement")
        self.assertIn("of 4", gate.value or "")
        self.assertIn("3 of 4", gate.required or "")

    def test_an_accepted_signal_passes_every_gate(self):
        now = datetime.now(timezone.utc)
        decision = build_signal("XAUUSD", self._trending(now), now=now)
        if decision.direction in ("CALL", "PUT"):
            self.assertTrue(all(c.passed for c in decision.checks),
                            [c.name for c in decision.checks if not c.passed])

    def test_gates_after_the_blocker_are_not_claimed_as_passed(self):
        """The engine really does stop at the first failure. Recording later
        gates as passed would be a more confident story than the truth."""
        now = datetime.now(timezone.utc)
        stale = self._trending(now - timedelta(hours=4))
        decision = build_signal("XAUUSD", stale, now=now)
        self.assertEqual(decision.direction, "NO_TRADE")
        names = [c.name for c in decision.checks]
        self.assertEqual(names[0], "Data freshness")
        self.assertFalse(decision.checks[0].passed)
        self.assertNotIn("Setup quality", names)

    def test_the_score_gate_reports_the_shortfall(self):
        now = datetime.now(timezone.utc)
        decision = build_signal("XAUUSD", self._trending(now), now=now,
                                technical_score_threshold=99)
        gate = next((c for c in decision.checks if c.name == "Setup quality"), None)
        self.assertIsNotNone(gate)
        self.assertFalse(gate.passed)
        self.assertIn("/100", gate.value or "")
        self.assertIn("99", gate.required or "")
