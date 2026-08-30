import unittest
from datetime import datetime, timedelta, timezone

from app.news.blackout import (
    ASSET_CURRENCIES, BlackoutConfig, EconomicEvent,
    evaluate_blackout, is_relevant, relevant_events,
)

UTC = timezone.utc
EVENT_TIME = datetime(2026, 8, 25, 12, 30, tzinfo=UTC)


def event(name="US CPI", currency="USD", impact="HIGH", at=EVENT_TIME) -> EconomicEvent:
    return EconomicEvent(event_name=name, currency=currency, event_time=at, impact=impact)


class TestRelevance(unittest.TestCase):
    def test_usd_news_is_relevant_to_every_configured_asset(self):
        e = event(currency="USD")
        for asset in ("XAUUSD", "EURUSD", "GBPUSD"):
            self.assertTrue(is_relevant(e, asset), asset)

    def test_gold_is_usd_sensitive_despite_having_no_currency_code(self):
        self.assertIn("USD", ASSET_CURRENCIES["XAUUSD"])
        self.assertTrue(is_relevant(event(currency="USD"), "XAUUSD"))

    def test_eur_news_does_not_affect_gbpusd_or_gold(self):
        e = event(currency="EUR")
        self.assertTrue(is_relevant(e, "EURUSD"))
        self.assertFalse(is_relevant(e, "GBPUSD"))
        self.assertFalse(is_relevant(e, "XAUUSD"))

    def test_gbp_news_only_affects_gbpusd(self):
        e = event(currency="GBP")
        self.assertTrue(is_relevant(e, "GBPUSD"))
        self.assertFalse(is_relevant(e, "EURUSD"))
        self.assertFalse(is_relevant(e, "XAUUSD"))

    def test_currency_matching_is_case_insensitive(self):
        self.assertTrue(is_relevant(event(currency="usd"), "XAUUSD"))

    def test_unknown_asset_matches_nothing(self):
        self.assertFalse(is_relevant(event(), "USDJPY"))

    def test_relevant_events_filters(self):
        events = [event(currency="USD"), event(currency="EUR"), event(currency="GBP")]
        self.assertEqual(len(relevant_events(events, "EURUSD")), 2)
        self.assertEqual(len(relevant_events(events, "XAUUSD")), 1)


class TestBlackoutWindows(unittest.TestCase):
    def test_clear_when_no_events(self):
        status = evaluate_blackout([], "XAUUSD", EVENT_TIME)
        self.assertFalse(status.active)
        self.assertEqual(status.phase, "CLEAR")

    def test_clear_well_before_the_event(self):
        status = evaluate_blackout([event()], "XAUUSD", EVENT_TIME - timedelta(hours=3))
        self.assertFalse(status.active)

    def test_paused_inside_the_pre_news_window(self):
        status = evaluate_blackout([event()], "XAUUSD", EVENT_TIME - timedelta(minutes=10))
        self.assertTrue(status.active)
        self.assertEqual(status.phase, "PRE_NEWS")
        self.assertIn("US CPI", status.reason)

    def test_paused_at_the_exact_event_moment(self):
        status = evaluate_blackout([event()], "XAUUSD", EVENT_TIME)
        self.assertTrue(status.active)
        self.assertEqual(status.phase, "POST_NEWS")

    def test_paused_inside_the_post_news_window(self):
        status = evaluate_blackout([event()], "XAUUSD", EVENT_TIME + timedelta(minutes=15))
        self.assertTrue(status.active)
        self.assertEqual(status.phase, "POST_NEWS")
        self.assertIn("stabilize", status.reason)

    def test_clear_once_the_post_news_window_has_passed(self):
        status = evaluate_blackout([event()], "XAUUSD", EVENT_TIME + timedelta(minutes=31))
        self.assertFalse(status.active)

    def test_boundaries_are_inclusive_of_the_window(self):
        exactly_before = evaluate_blackout([event()], "XAUUSD", EVENT_TIME - timedelta(minutes=30))
        exactly_after = evaluate_blackout([event()], "XAUUSD", EVENT_TIME + timedelta(minutes=30))
        self.assertTrue(exactly_before.active)
        self.assertTrue(exactly_after.active)

    def test_medium_and_low_impact_never_pause_trading(self):
        for impact in ("MEDIUM", "LOW"):
            status = evaluate_blackout([event(impact=impact)], "XAUUSD", EVENT_TIME)
            self.assertFalse(status.active, impact)

    def test_irrelevant_currency_does_not_pause(self):
        status = evaluate_blackout([event(currency="EUR")], "GBPUSD", EVENT_TIME)
        self.assertFalse(status.active)

    def test_nearest_event_is_the_one_reported(self):
        near = event(name="Near event", at=EVENT_TIME)
        far = event(name="Far event", at=EVENT_TIME + timedelta(minutes=25))
        status = evaluate_blackout([far, near], "XAUUSD", EVENT_TIME + timedelta(minutes=2))
        self.assertEqual(status.event_name, "Near event")


class TestConfigurability(unittest.TestCase):
    def test_wider_window_pauses_earlier(self):
        wide = BlackoutConfig(minutes_before=120, minutes_after=30)
        at = EVENT_TIME - timedelta(minutes=90)
        self.assertFalse(evaluate_blackout([event()], "XAUUSD", at).active)
        self.assertTrue(evaluate_blackout([event()], "XAUUSD", at, wide).active)

    def test_zero_windows_only_pause_at_the_exact_moment(self):
        tight = BlackoutConfig(minutes_before=0, minutes_after=0)
        self.assertTrue(evaluate_blackout([event()], "XAUUSD", EVENT_TIME, tight).active)
        self.assertFalse(
            evaluate_blackout([event()], "XAUUSD", EVENT_TIME + timedelta(minutes=1), tight).active
        )

    def test_negative_window_rejected(self):
        with self.assertRaises(ValueError):
            BlackoutConfig(minutes_before=-1)


class TestMisuse(unittest.TestCase):
    def test_naive_now_rejected(self):
        with self.assertRaises(ValueError):
            evaluate_blackout([], "XAUUSD", datetime(2026, 8, 25, 12, 30))

    def test_naive_event_time_rejected(self):
        naive = EconomicEvent("X", "USD", datetime(2026, 8, 25, 12, 30), "HIGH")
        with self.assertRaises(ValueError):
            evaluate_blackout([naive], "XAUUSD", EVENT_TIME)


if __name__ == "__main__":
    unittest.main()
