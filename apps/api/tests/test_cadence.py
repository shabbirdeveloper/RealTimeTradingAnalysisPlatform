"""
The cadence exists to buy fresher entries without walking off the
provider's daily cliff, so the budget is the thing most worth asserting:
a future edit that makes polling faster should fail here, loudly, rather
than at 10am when the quota runs out and the day's data stops.
"""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from app.collector.cadence import (
    ACTIVE_END_HOUR,
    ACTIVE_START_HOUR,
    CONTINUOUS_CADENCE,
    FREE_TIER_REQUESTS_PER_DAY,
    FX_CADENCE,
    TICK_SECONDS,
    cadence_for,
    daily_request_estimate,
    interval_seconds,
    is_active_hours,
    should_poll,
)

ALL_ASSETS = ["XAUUSD", "EURUSD", "GBPUSD", "BTCUSD", "ETHUSD"]


def at(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 9, 2, hour, minute, tzinfo=timezone.utc)


class BudgetTests(unittest.TestCase):
    def test_default_configuration_fits_the_free_tier(self):
        estimate = daily_request_estimate(ALL_ASSETS)
        self.assertLess(
            estimate, FREE_TIER_REQUESTS_PER_DAY,
            f"{estimate:.0f} requests/day exceeds the {FREE_TIER_REQUESTS_PER_DAY} cap -- "
            "the collector would run out of quota partway through the day and "
            "then have NO data at all, which is worse than polling slower.",
        )

    def test_budget_keeps_headroom_for_retries(self):
        """A retry, a restart, a backfill all cost extra requests. Sitting at
        799/800 means the first hiccup is also an outage."""
        self.assertLess(daily_request_estimate(ALL_ASSETS), FREE_TIER_REQUESTS_PER_DAY * 0.95)

    def test_estimate_grows_with_assets(self):
        self.assertGreater(daily_request_estimate(ALL_ASSETS), daily_request_estimate(ALL_ASSETS[:3]))


class CadenceTests(unittest.TestCase):
    def test_forex_is_faster_during_london_and_new_york(self):
        self.assertEqual(interval_seconds("EURUSD", at(10)), 300)
        self.assertEqual(interval_seconds("EURUSD", at(3)), 900)

    def test_crypto_cadence_does_not_change_with_the_session(self):
        """Crypto has no London open. Treating it as if it did would spend
        forex-grade credits on a market that isn't keeping those hours."""
        self.assertEqual(interval_seconds("BTCUSD", at(10)), interval_seconds("BTCUSD", at(3)))

    def test_continuous_instruments_use_the_continuous_cadence(self):
        self.assertEqual(cadence_for("BTCUSD"), CONTINUOUS_CADENCE)
        self.assertEqual(cadence_for("XAUUSD"), FX_CADENCE)

    def test_active_window_matches_the_session_engine(self):
        """Must agree with features.structure.session_for_time, or the
        collector speeds up at a different moment than the engine believes
        the session started."""
        from app.features.structure import session_for_time

        self.assertNotEqual(session_for_time(at(ACTIVE_START_HOUR)), "ASIAN")
        self.assertEqual(session_for_time(at(ACTIVE_END_HOUR)), "ASIAN")

    def test_boundaries_are_half_open(self):
        self.assertTrue(is_active_hours(at(ACTIVE_START_HOUR)))
        self.assertFalse(is_active_hours(at(ACTIVE_START_HOUR - 1, 59)))
        self.assertFalse(is_active_hours(at(ACTIVE_END_HOUR)))

    def test_every_cadence_divides_the_tick_evenly(self):
        """An interval that isn't a multiple of the tick drifts later every
        cycle, so the real cadence is never the configured one."""
        for seconds in (
            FX_CADENCE.active_seconds, FX_CADENCE.quiet_seconds,
            CONTINUOUS_CADENCE.active_seconds, CONTINUOUS_CADENCE.quiet_seconds,
        ):
            self.assertEqual(seconds % TICK_SECONDS, 0, f"{seconds}s is not a multiple of the {TICK_SECONDS}s tick")


class DueTests(unittest.TestCase):
    def test_first_cycle_after_restart_always_polls(self):
        self.assertTrue(should_poll("EURUSD", at(10), None))

    def test_not_due_until_the_interval_has_passed(self):
        now = at(10, 3)
        self.assertFalse(should_poll("EURUSD", now, now - timedelta(seconds=120)))
        self.assertTrue(should_poll("EURUSD", now, now - timedelta(seconds=300)))

    def test_a_hair_early_still_counts(self):
        """The scheduler fires a couple of seconds off. Without tolerance an
        asset that misses its slot waits a whole extra tick, halving its
        real cadence."""
        now = at(10)
        self.assertTrue(should_poll("EURUSD", now, now - timedelta(seconds=297)))

    def test_crypto_waits_longer_than_forex_at_the_same_moment(self):
        now = at(10)
        last = now - timedelta(seconds=600)
        self.assertTrue(should_poll("EURUSD", now, last))
        self.assertFalse(should_poll("BTCUSD", now, last))


if __name__ == "__main__":
    unittest.main()
