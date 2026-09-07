"""Tests for the rebuilt OTC engine (spec Phase 50).

The emphasis is on the REFUSALS. Any scorer can be made to emit CALL; the
value of this engine is supposed to be that it declines, so the gates get
the coverage. Each test names the market it is describing, because a
failure here should say what stopped working, not just which assertion
tripped.
"""

from __future__ import annotations

import random
import unittest
from datetime import datetime, timedelta, timezone

from app.otc.config import CONFIG, TIMEFRAME_SECONDS
from app.otc.engine import evaluate
from app.otc.features import build_context
from app.otc.filters import entry_timing_failures, scoring_failures, warmup_failures
from app.otc.health import FeedStatus, assess
from app.otc.regime import CHOPPY, UNKNOWN
from app.otc.routing import ROUTING, strategies_for
from app.otc.signal import Direction, SignalStatus
from app.otc.strategies.base import MAX_TOTAL, SideScore, StrategyVerdict

NOW = datetime(2026, 9, 5, 12, 0, tzinfo=timezone.utc)


def make_series(count: int, seconds: int, *, start=500.0, drift=0.0, noise=0.3, seed=1):
    rnd = random.Random(seed)
    out, price = [], start
    t0 = NOW - timedelta(seconds=seconds * count)
    for i in range(count):
        open_ = price
        price = price + drift + rnd.gauss(0, noise)
        out.append({
            "open_time": t0 + timedelta(seconds=seconds * i),
            "open": open_,
            "high": max(open_, price) + abs(rnd.gauss(0, noise / 2)),
            "low": min(open_, price) - abs(rnd.gauss(0, noise / 2)),
            "close": price,
        })
    return out


def full_market(count=200, **kw):
    return {tf: make_series(count, secs, **kw) for tf, secs in TIMEFRAME_SECONDS.items()}


def healthy():
    return assess("DERIV_V75", last_tick_at=NOW - timedelta(seconds=2), ticks_per_minute=30, now=NOW)


class FeedHealthTests(unittest.TestCase):
    def test_never_ticked_is_disconnected_not_stale(self):
        h = assess("DERIV_V75", last_tick_at=None, ticks_per_minute=0, now=NOW)
        self.assertIs(h.status, FeedStatus.DISCONNECTED)
        self.assertFalse(h.may_signal)

    def test_thin_feed_is_degraded_not_healthy(self):
        # Current prices, but too few ticks for sub-minute bars to mean
        # anything. Reporting this as HEALTHY is how noise becomes a range.
        h = assess("DERIV_V75", last_tick_at=NOW, ticks_per_minute=2, now=NOW)
        self.assertIs(h.status, FeedStatus.DEGRADED)
        self.assertFalse(h.may_signal)

    def test_only_healthy_may_signal(self):
        for status in FeedStatus:
            self.assertEqual(status.may_signal, status is FeedStatus.HEALTHY)


class FeedGateTests(unittest.TestCase):
    def test_unhealthy_feed_blocks_regardless_of_market(self):
        """Phase 53: there is no override, so no market may bypass it."""
        stale = assess("DERIV_V75", last_tick_at=NOW - timedelta(minutes=5),
                       ticks_per_minute=30, now=NOW)
        decision = evaluate("DERIV_V75", full_market(drift=0.4), NOW, stale)
        self.assertIs(decision.direction, Direction.NO_TRADE)
        self.assertIs(decision.status, SignalStatus.REJECTED)
        self.assertTrue(any("feed" in r for r in decision.rejection_reasons))

    def test_rejection_always_carries_a_reason(self):
        """A NO_TRADE with no reason is indistinguishable from a bug."""
        for drift in (-0.4, 0.0, 0.4):
            decision = evaluate("DERIV_V75", full_market(drift=drift), NOW, healthy())
            if not decision.is_signal:
                self.assertTrue(decision.rejection_reasons, f"silent NO_TRADE at drift {drift}")


class WarmupTests(unittest.TestCase):
    def test_short_history_is_refused(self):
        thin = {tf: make_series(20, secs) for tf, secs in TIMEFRAME_SECONDS.items()}
        decision = evaluate("DERIV_V75", thin, NOW, healthy())
        self.assertIs(decision.direction, Direction.NO_TRADE)
        self.assertTrue(any("bars" in r or "converge" in r for r in decision.rejection_reasons))

    def test_missing_timeframe_is_named(self):
        market = full_market()
        del market["M3"]
        problems = warmup_failures(build_context("DERIV_V75", NOW, market))
        self.assertTrue(any("M3" in p for p in problems))


class RoutingTests(unittest.TestCase):
    def test_choppy_and_unknown_route_to_nothing(self):
        """The most important entries in the table."""
        self.assertEqual(strategies_for(CHOPPY), [])
        self.assertEqual(strategies_for(UNKNOWN), [])

    def test_only_unreadable_regimes_route_to_nothing(self):
        """A regime the classifier COULD read must reach a strategy.
        Routing a readable regime to nothing silences the engine for as
        long as the market stays in it, and that silence is indis-
        tinguishable from a quiet market."""
        from app.otc import regime as R
        readable = {
            R.TRENDING_UP, R.TRENDING_DOWN, R.RANGING, R.BREAKOUT,
            R.PULLBACK, R.HIGH_VOLATILITY, R.LOW_VOLATILITY,
        }
        for name in readable:
            self.assertTrue(strategies_for(name), f"{name} routes to no strategy")

    def test_every_regime_has_an_explicit_route(self):
        from app.otc import regime as R
        declared = {
            R.TRENDING_UP, R.TRENDING_DOWN, R.RANGING, R.BREAKOUT, R.PULLBACK,
            R.HIGH_VOLATILITY, R.LOW_VOLATILITY, R.CHOPPY, R.UNKNOWN,
        }
        self.assertEqual(declared, set(ROUTING), "a regime with no routing entry falls through")

    def test_unrecognised_regime_fails_closed(self):
        self.assertEqual(strategies_for("SOMETHING_NEW"), [])


class ScoringGateTests(unittest.TestCase):
    def _verdict(self, call: int, put: int) -> StrategyVerdict:
        c, p = SideScore(), SideScore()
        c.trend, c.structure, c.momentum = min(20, call), min(20, max(0, call - 20)), max(0, call - 40)
        p.trend, p.structure, p.momentum = min(20, put), min(20, max(0, put - 20)), max(0, put - 40)
        return StrategyVerdict("t", c, p)

    def test_high_score_with_thin_separation_is_refused(self):
        """The spec's own example: CALL 79 / PUT 68 must not signal."""
        problems = scoring_failures(self._verdict(79, 68))
        self.assertTrue(any("separation" in p for p in problems))

    def test_clear_separation_at_a_good_score_passes(self):
        self.assertEqual(scoring_failures(self._verdict(84, 39)), [])

    def test_wide_separation_at_a_low_score_is_still_refused(self):
        # 40 vs 5 separates cleanly but neither side has evidence.
        problems = scoring_failures(self._verdict(40, 5))
        self.assertTrue(any("below the" in p and "floor" in p for p in problems))

    def test_a_tie_is_never_a_signal(self):
        self.assertTrue(scoring_failures(self._verdict(80, 80)))


class ScoreBudgetTests(unittest.TestCase):
    def test_categories_sum_to_one_hundred(self):
        self.assertEqual(MAX_TOTAL, 100)

    def test_award_cannot_exceed_its_category(self):
        side = SideScore()
        side.award("momentum", 500, "absurd")
        self.assertEqual(side.momentum, 20)

    def test_unread_categories_score_zero_not_half(self):
        """A market a strategy cannot read must produce a LOW score, so the
        minimum-score gate rejects ignorance as well as disagreement."""
        self.assertEqual(SideScore().total, 0)

    def test_scores_need_not_sum_to_one_hundred(self):
        c, p = SideScore(), SideScore()
        c.award("trend", 10, "x")
        p.award("trend", 10, "y")
        verdict = StrategyVerdict("t", c, p)
        self.assertEqual(verdict.call_total + verdict.put_total, 20)
        self.assertIsNone(verdict.leader)


class EntryTimingTests(unittest.TestCase):
    def _context(self, *, spike_direction: str | None):
        market = full_market()
        if spike_direction:
            entry = market["S30"]
            last = entry[-1]
            atr_guess = 3.0
            if spike_direction == "up":
                last["open"], last["low"] = last["close"] - atr_guess, last["close"] - atr_guess
                last["high"] = last["close"]
            else:
                last["open"], last["high"] = last["close"] + atr_guess, last["close"] + atr_guess
                last["low"] = last["close"]
        return build_context("DERIV_V75", NOW, market)

    def test_call_straight_after_a_bullish_spike_is_refused(self):
        problems = entry_timing_failures(self._context(spike_direction="up"), "CALL")
        self.assertTrue(problems, "a CALL immediately after a large bullish candle must be refused")

    def test_put_straight_after_a_bearish_spike_is_refused(self):
        problems = entry_timing_failures(self._context(spike_direction="down"), "PUT")
        self.assertTrue(problems)

    def test_missing_entry_timeframe_refuses_rather_than_passes(self):
        market = full_market()
        del market["S30"]
        del market["M1"]
        problems = entry_timing_failures(build_context("DERIV_V75", NOW, market), "CALL")
        self.assertTrue(problems)


class FingerprintTests(unittest.TestCase):
    def test_same_setup_re_evaluated_keeps_its_identity(self):
        """Phase 26: a setup rescored 83 -> 84 thirty seconds later is the
        same setup, and the cooldown depends on recognising that."""
        from app.otc.engine import _fingerprint
        c1, p1 = SideScore(), SideScore()
        c1.trend, p1.trend = 20, 4
        c2, p2 = SideScore(), SideScore()
        c2.trend, p2.trend = 19, 5
        a = _fingerprint("DERIV_V75", "CALL", StrategyVerdict("s", c1, p1), "TRENDING_UP")
        b = _fingerprint("DERIV_V75", "CALL", StrategyVerdict("s", c2, p2), "TRENDING_UP")
        self.assertEqual(a, b)

    def test_opposite_direction_is_a_different_setup(self):
        from app.otc.engine import _fingerprint
        c, p = SideScore(), SideScore()
        c.trend, p.trend = 20, 4
        v = StrategyVerdict("s", c, p)
        self.assertNotEqual(
            _fingerprint("DERIV_V75", "CALL", v, "TRENDING_UP"),
            _fingerprint("DERIV_V75", "PUT", v, "TRENDING_UP"),
        )


class ConfigTests(unittest.TestCase):
    def test_exactly_one_instrument_is_enabled(self):
        """Phase 1 is a hard constraint, not a preference."""
        from app.otc.config import enabled_symbols
        self.assertEqual(enabled_symbols(), ["DERIV_V75"])

    def test_expiry_is_five_minutes(self):
        self.assertEqual(CONFIG.expiry_seconds, 300)

    def test_evaluation_is_per_closed_thirty_second_bar(self):
        self.assertEqual(CONFIG.evaluation_timeframe, "S30")


class DeterminismTests(unittest.TestCase):
    def test_the_same_input_yields_the_same_decision(self):
        """Replay and live must be identical, so the engine must have no
        hidden state and no clock of its own."""
        market = full_market(drift=0.25)
        a = evaluate("DERIV_V75", market, NOW, healthy())
        b = evaluate("DERIV_V75", market, NOW, healthy())
        self.assertEqual(
            (a.direction, a.call_score, a.put_score, a.regime, a.strategy),
            (b.direction, b.call_score, b.put_score, b.regime, b.strategy),
        )


if __name__ == "__main__":
    unittest.main()


class ProfileTests(unittest.TestCase):
    """The two data sources publish different timeframes, and the engine
    must not pretend otherwise. A quote vendor has no sub-minute bars, so
    an engine that asked for S30 and proceeded without it would be scoring
    entry timing on evidence it never had."""

    def test_real_market_profile_has_no_sub_minute_timeframes(self):
        from app.otc.config import REAL_MARKET_PROFILE
        for tf in REAL_MARKET_PROFILE.timeframes:
            self.assertFalse(tf.startswith("S"), f"{tf} cannot come from a quote vendor")

    def test_real_market_entry_timeframe_is_m1(self):
        from app.otc.config import REAL_MARKET_PROFILE
        self.assertEqual(REAL_MARKET_PROFILE.entry, "M1")

    def test_both_profiles_share_the_five_minute_expiry(self):
        from app.otc.config import OTC_PROFILE, REAL_MARKET_PROFILE
        self.assertEqual(OTC_PROFILE.expiry_seconds, 300)
        self.assertEqual(REAL_MARKET_PROFILE.expiry_seconds, 300)

    def test_profile_is_chosen_by_symbol(self):
        from app.otc.config import OTC_PROFILE, REAL_MARKET_PROFILE, profile_for
        self.assertIs(profile_for("DERIV_V75"), OTC_PROFILE)
        self.assertIs(profile_for("EURUSD"), REAL_MARKET_PROFILE)

    def test_real_market_market_runs_without_sub_minute_data(self):
        """The whole point: the same engine, on four timeframes, reaches a
        decision instead of failing warm-up on a missing S30."""
        from app.otc.config import REAL_MARKET_PROFILE
        market = {tf: make_series(200, TIMEFRAME_SECONDS[tf], drift=0.2)
                  for tf in REAL_MARKET_PROFILE.timeframes}
        decision = evaluate("EURUSD", market, NOW, healthy(), REAL_MARKET_PROFILE)
        self.assertNotIn("S30", " ".join(decision.rejection_reasons))
        self.assertEqual(decision.expiry_seconds, 300)

    def test_every_derived_timeframe_is_a_whole_multiple_of_m1(self):
        """M3 and M1 cannot be built from M5, which is why the collector
        fetches M1 and aggregates upward."""
        from app.otc.config import REAL_MARKET_PROFILE
        for tf in REAL_MARKET_PROFILE.timeframes:
            self.assertEqual(TIMEFRAME_SECONDS[tf] % 60, 0, f"{tf} is not a whole minute")
