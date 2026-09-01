import unittest
from datetime import datetime, timedelta, timezone

from app.features.signal_engine import _expiry_weight, build_signal
from app.features.strategy import default_strategy, format_expiry
from app.instruments import (
    OTC_PROFILE,
    PUBLIC_MARKET_PROFILE,
    FeedDescriptor,
    FeedKind,
    TradingProfile,
    get_instrument,
)
from tests.test_signal_engine import make_candles

QUOTEX = FeedDescriptor("quotex_otc", FeedKind.BROKER_OTC, broker="QUOTEX")


def otc_history(ending_at=None, drift=0.00004) -> dict:
    """A trending series on the OTC ladder. Step sizes in SECONDS, which is
    the entire point -- this could not be expressed at all while every
    duration was an integer number of minutes."""
    ending_at = ending_at or datetime.now(timezone.utc)
    steps = {"M5": 5, "M1": 1, "S30": 0.5, "S15": 0.25}
    return {
        tf: make_candles(300, 1.1000, drift * mins, mins, ending_at=ending_at)
        for tf, mins in steps.items()
    }


class ProfilesDescribeTheirInstrument(unittest.TestCase):
    def test_real_markets_keep_the_ladder_and_horizons_they_always_had(self):
        p = get_instrument("EURUSD").profile
        self.assertEqual(p.timeframes, ("H4", "H1", "M15", "M5"))
        self.assertEqual(p.entry_timeframe, "M5")
        self.assertEqual(p.expiries_seconds, (900, 1800, 3600))

    def test_otc_reasons_in_minutes_and_expires_in_seconds(self):
        p = get_instrument("EURUSD_OTC").profile
        self.assertEqual(p.timeframes, ("M5", "M1", "S30", "S15"))
        self.assertEqual(p.entry_timeframe, "S15")
        self.assertTrue(all(e <= 180 for e in p.expiries_seconds))

    def test_staleness_limit_scales_with_the_entry_timeframe(self):
        """15 minutes of staleness is a minor gap on M5 and an eternity on
        S15. A single global limit would make the OTC gate useless."""
        self.assertGreater(
            PUBLIC_MARKET_PROFILE.max_data_age_seconds,
            OTC_PROFILE.max_data_age_seconds * 10,
        )

    def test_entry_timeframe_must_be_the_fastest_rung(self):
        """'Last element of the tuple' is an easy thing to silently reorder."""
        with self.assertRaises(ValueError):
            TradingProfile(
                timeframes=("M5", "M1"), entry_timeframe="M5",
                expiries_seconds=(60,), max_data_age_seconds=60,
            )

    def test_a_profile_must_offer_an_expiry(self):
        with self.assertRaises(ValueError):
            TradingProfile(
                timeframes=("M5",), entry_timeframe="M5",
                expiries_seconds=(), max_data_age_seconds=60,
            )


class ExpiryWeighting(unittest.TestCase):
    """The weighting used to be a table keyed on the literal values 15/30/60.
    Any expiry outside that table fell through to neutral weights, so OTC's
    five second-scale horizons would all have scored identically."""

    def test_shortest_expiry_leans_on_the_fastest_timeframe(self):
        w = {tf: _expiry_weight(15, tf, OTC_PROFILE) for tf in OTC_PROFILE.timeframes}
        self.assertGreater(w["S15"], w["M5"])

    def test_longest_expiry_leans_on_the_slowest_timeframe(self):
        w = {tf: _expiry_weight(180, tf, OTC_PROFILE) for tf in OTC_PROFILE.timeframes}
        self.assertGreater(w["M5"], w["S15"])

    def test_the_extremes_match_the_historical_real_market_table(self):
        """The hand-tuned table's endpoints were 0.6 and 1.4. The computed
        ramp must still hit those, or every existing score shifts."""
        self.assertAlmostEqual(_expiry_weight(900, "M5", PUBLIC_MARKET_PROFILE), 1.4)
        self.assertAlmostEqual(_expiry_weight(900, "H4", PUBLIC_MARKET_PROFILE), 0.6)
        self.assertAlmostEqual(_expiry_weight(3600, "M5", PUBLIC_MARKET_PROFILE), 0.6)
        self.assertAlmostEqual(_expiry_weight(3600, "H4", PUBLIC_MARKET_PROFILE), 1.4)

    def test_the_middle_expiry_is_neutral(self):
        for tf in PUBLIC_MARKET_PROFILE.timeframes:
            self.assertAlmostEqual(_expiry_weight(1800, tf, PUBLIC_MARKET_PROFILE), 1.0)

    def test_every_expiry_scores_differently(self):
        """The failure the old table had: unlisted expiries all collapsing to
        the same neutral weights and becoming indistinguishable."""
        seen = {
            tuple(round(_expiry_weight(e, tf, OTC_PROFILE), 6) for tf in OTC_PROFILE.timeframes)
            for e in OTC_PROFILE.expiries_seconds
        }
        self.assertEqual(len(seen), len(OTC_PROFILE.expiries_seconds))


class OtcSignalsUseSecondScaleHorizons(unittest.TestCase):
    def test_an_otc_decision_picks_a_second_scale_expiry(self):
        decision = build_signal(
            "EURUSD_OTC", otc_history(), now=datetime.now(timezone.utc), feed=QUOTEX,
        )
        if decision.expiry_seconds is not None:
            self.assertIn(decision.expiry_seconds, OTC_PROFILE.expiries_seconds)
            self.assertLessEqual(decision.expiry_seconds, 180)

    def test_otc_candidates_cover_the_whole_profile(self):
        decision = build_signal(
            "EURUSD_OTC", otc_history(), now=datetime.now(timezone.utc), feed=QUOTEX,
        )
        if decision.candidates:
            self.assertEqual(
                sorted(c.expiry_seconds for c in decision.candidates),
                sorted(OTC_PROFILE.expiries_seconds),
            )

    def test_otc_staleness_gate_fires_on_a_gap_a_real_market_would_tolerate(self):
        """Five minutes of silence is nothing on an M5 ladder and fatal on a
        15-second one. The gate has to scale or it protects nothing."""
        now = datetime.now(timezone.utc)
        history = otc_history(ending_at=now - timedelta(minutes=5))
        decision = build_signal("EURUSD_OTC", history, now=now, feed=QUOTEX)
        self.assertEqual(decision.direction, "NO_TRADE")
        self.assertTrue(any("stale" in w.lower() for w in decision.warnings), decision.warnings)

    def test_a_fresh_otc_series_is_not_stale(self):
        now = datetime.now(timezone.utc)
        decision = build_signal("EURUSD_OTC", otc_history(ending_at=now), now=now, feed=QUOTEX)
        self.assertFalse(any("stale" in w.lower() for w in decision.warnings), decision.warnings)

    def test_the_otc_default_strategy_covers_its_own_expiries(self):
        strategy = default_strategy(
            "EURUSD_OTC", expiries=get_instrument("EURUSD_OTC").profile.expiries_seconds
        )
        self.assertEqual(strategy.expiries, tuple(sorted(OTC_PROFILE.expiries_seconds)))


class ExpiryFormatting(unittest.TestCase):
    def test_reads_naturally_at_both_scales(self):
        self.assertEqual(format_expiry(15), "15s")
        self.assertEqual(format_expiry(60), "1m")
        self.assertEqual(format_expiry(180), "3m")
        self.assertEqual(format_expiry(900), "15m")
        self.assertEqual(format_expiry(3600), "60m")

    def test_awkward_values_do_not_lose_their_seconds(self):
        self.assertEqual(format_expiry(90), "1m30s")


if __name__ == "__main__":
    unittest.main()
