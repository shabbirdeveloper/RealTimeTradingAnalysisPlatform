import unittest
from datetime import datetime, timedelta, timezone

from app.features.decision_identity import primary_note
from app.features.signal_engine import build_signal
from app.features.strategy import (
    ALL_REGIMES,
    ALL_SESSIONS,
    AssetStrategy,
    StrategyConfig,
    default_strategy,
    fingerprint,
    strategy_from_rows,
    summarize_overrides,
    version_string,
)
from tests.test_signal_engine import make_candles


def _tuned(asset: str, expiry: int, **kwargs) -> AssetStrategy:
    """Stock strategy with one expiry's config replaced."""
    base = default_strategy(asset)
    by_expiry = dict(base.by_expiry)
    by_expiry[expiry] = StrategyConfig(expiry_minutes=expiry, **kwargs)
    return AssetStrategy(asset=asset, label=base.label, by_expiry=by_expiry)


class DefaultsAreABaseline(unittest.TestCase):
    """The whole point of shipping permissive defaults is that adding the
    apparatus does not move a single signal. If these fail, the two weeks of
    history accumulating now is not comparable to anything measured later."""

    def test_defaults_match_the_engines_historical_constants(self):
        for expiry in (15, 30, 60):
            cfg = default_strategy("XAUUSD").for_expiry(expiry)
            self.assertEqual(cfg.min_technical_score, 78)
            self.assertEqual(cfg.allowed_regimes, ALL_REGIMES)
            self.assertEqual(cfg.allowed_sessions, ALL_SESSIONS)
            self.assertTrue(cfg.enabled)

    def test_default_config_never_declines_on_regime_or_session(self):
        cfg = default_strategy("XAUUSD").for_expiry(30)
        for regime in ALL_REGIMES:
            for session in ALL_SESSIONS:
                self.assertIsNone(
                    cfg.rejection_reason(regime=regime, session=session, technical_score=78)
                )

    def test_stock_strategy_reports_no_overrides(self):
        self.assertEqual(summarize_overrides(default_strategy("EURUSD")), [])

    def test_explicit_default_strategy_matches_omitting_it(self):
        history = _trending("XAUUSD")
        now = datetime.now(timezone.utc)
        implicit = build_signal("XAUUSD", history, now=now)
        explicit = build_signal("XAUUSD", history, now=now, strategy=default_strategy("XAUUSD"))
        self.assertEqual(implicit.direction, explicit.direction)
        self.assertEqual(implicit.technical_score, explicit.technical_score)
        self.assertEqual(implicit.expiry_minutes, explicit.expiry_minutes)
        self.assertEqual(implicit.strategy_version, explicit.strategy_version)


class VersionStamping(unittest.TestCase):
    def test_every_signal_carries_a_version(self):
        d = build_signal("XAUUSD", _trending("XAUUSD"), now=datetime.now(timezone.utc))
        self.assertTrue(d.strategy_version.startswith("v1:"))

    def test_no_trade_paths_are_stamped_too(self):
        """A decision that exits early through the staleness gate is still
        evidence about the rule set in force. Losing its stamp would bias the
        recorded sample toward cycles that reached the end of the function."""
        now = datetime.now(timezone.utc)
        stale = _trending("XAUUSD", ending_at=now - timedelta(hours=4))
        d = build_signal("XAUUSD", stale, now=now)
        self.assertEqual(d.direction, "NO_TRADE")
        self.assertTrue(d.strategy_version.startswith("v1:"))

    def test_changing_any_knob_changes_the_fingerprint(self):
        base = default_strategy("XAUUSD")
        variants = [
            _tuned("XAUUSD", 30, min_technical_score=85),
            _tuned("XAUUSD", 30, enabled=False),
            _tuned("XAUUSD", 30, allowed_regimes=frozenset({"TRENDING_UP"})),
            _tuned("XAUUSD", 30, allowed_sessions=frozenset({"LONDON"})),
        ]
        seen = {fingerprint(base)}
        for v in variants:
            fp = fingerprint(v)
            self.assertNotIn(fp, seen, "two different rule sets fingerprinted the same")
            seen.add(fp)

    def test_forgetting_to_bump_the_label_still_yields_a_new_version(self):
        """The label is for humans; the fingerprint is what guarantees
        attribution. Forgetting to relabel must cost clarity, not correctness."""
        stock = default_strategy("XAUUSD")
        tuned = _tuned("XAUUSD", 15, min_technical_score=88)
        self.assertEqual(stock.label, tuned.label)
        self.assertNotEqual(version_string(stock), version_string(tuned))

    def test_same_numbers_on_different_assets_are_different_rule_sets(self):
        """Spec section 4: do not assume parameters transfer between assets.
        Pooling XAUUSD and EURUSD history under one version would do exactly
        that, silently."""
        self.assertNotEqual(
            version_string(default_strategy("XAUUSD")),
            version_string(default_strategy("EURUSD")),
        )

    def test_fingerprint_is_stable_across_set_ordering(self):
        a = _tuned("XAUUSD", 30, allowed_sessions=frozenset({"LONDON", "NEW_YORK"}))
        b = _tuned("XAUUSD", 30, allowed_sessions=frozenset({"NEW_YORK", "LONDON"}))
        self.assertEqual(fingerprint(a), fingerprint(b))


class GatesNarrowButNeverWiden(unittest.TestCase):
    def test_raising_the_score_bar_can_turn_a_signal_into_no_trade(self):
        history, now = _trending("XAUUSD"), datetime.now(timezone.utc)
        accepted = build_signal("XAUUSD", history, now=now)
        self.assertIn(accepted.direction, ("CALL", "PUT"))

        strict = AssetStrategy(
            asset="XAUUSD", label="v1",
            by_expiry={e: StrategyConfig(expiry_minutes=e, min_technical_score=99) for e in (15, 30, 60)},
        )
        declined = build_signal("XAUUSD", history, now=now, strategy=strict)
        self.assertEqual(declined.direction, "NO_TRADE")
        # Still recorded as a rejected OPPORTUNITY, not a blank no-setup cycle:
        # this is precisely the row shadow resolution needs to tell you whether
        # tightening the bar was right.
        self.assertEqual(declined.rejected_opportunity_direction, accepted.direction)

    def test_session_gate_declines_and_says_so(self):
        history, now = _trending("XAUUSD"), datetime.now(timezone.utc)
        live = build_signal("XAUUSD", history, now=now)
        blocked_session = live.session

        strategy = AssetStrategy(
            asset="XAUUSD", label="v1",
            by_expiry={
                e: StrategyConfig(
                    expiry_minutes=e,
                    allowed_sessions=frozenset(ALL_SESSIONS - {blocked_session}),
                )
                for e in (15, 30, 60)
            },
        )
        d = build_signal("XAUUSD", history, now=now, strategy=strategy)
        self.assertEqual(d.direction, "NO_TRADE")
        self.assertTrue(
            any("session is not permitted" in w for w in d.warnings),
            f"expected a session explanation, got {d.warnings}",
        )

    def test_declined_expiry_records_which_gate_stopped_it(self):
        """A score and a session block are different problems calling for
        different fixes; after the fact the score alone cannot tell them apart."""
        history, now = _trending("XAUUSD"), datetime.now(timezone.utc)
        session = build_signal("XAUUSD", history, now=now).session
        strategy = AssetStrategy(
            asset="XAUUSD", label="v1",
            by_expiry={
                15: StrategyConfig(expiry_minutes=15, allowed_sessions=frozenset(ALL_SESSIONS - {session})),
                30: StrategyConfig(expiry_minutes=30, min_technical_score=99),
                60: StrategyConfig(expiry_minutes=60, enabled=False),
            },
        )
        d = build_signal("XAUUSD", history, now=now, strategy=strategy)
        by_expiry = {c.expiry_minutes: c.rejection_reason for c in d.candidates}
        self.assertIn("session is not permitted", by_expiry[15])
        self.assertIn("below the 99 minimum", by_expiry[30])
        self.assertIn("disabled", by_expiry[60])

    def test_config_cannot_re_enable_a_regime_the_engine_stands_down_on(self):
        """HIGH_VOLATILITY/UNSTABLE are a safety rule above the config layer.
        Listing them in allowed_regimes must not buy a signal -- config
        narrows behaviour, it never widens it past a safety stop."""
        now = datetime.now(timezone.utc)
        history = _unstable("XAUUSD", ending_at=now)
        permissive = AssetStrategy(
            asset="XAUUSD", label="v1",
            by_expiry={
                e: StrategyConfig(expiry_minutes=e, min_technical_score=0, allowed_regimes=ALL_REGIMES)
                for e in (15, 30, 60)
            },
        )
        d = build_signal("XAUUSD", history, now=now, strategy=permissive)
        self.assertEqual(d.direction, "NO_TRADE")

    def test_overrides_are_surfaced_on_an_accepted_signal(self):
        history, now = _trending("XAUUSD"), datetime.now(timezone.utc)
        strategy = _tuned("XAUUSD", 60, min_technical_score=40)
        d = build_signal("XAUUSD", history, now=now, strategy=strategy)
        if d.direction in ("CALL", "PUT"):
            self.assertTrue(any("Strategy overrides in force" in r for r in d.reasons))

    def test_threshold_sweep_kwarg_still_overrides_every_expiry(self):
        """The backtester's minimum-confidence sweep must keep working, and
        must win over whatever the stored config says -- otherwise a sweep
        would silently measure the live config instead of the swept value."""
        history, now = _trending("XAUUSD"), datetime.now(timezone.utc)
        d = build_signal(
            "XAUUSD", history, now=now,
            strategy=_tuned("XAUUSD", 30, min_technical_score=10),
            technical_score_threshold=99,
        )
        self.assertEqual(d.direction, "NO_TRADE")
        for c in d.candidates:
            self.assertIn("below the 99 minimum", c.rejection_reason or "")


class ConfigLoadedFromRows(unittest.TestCase):
    def test_absent_rows_yield_the_shipped_defaults(self):
        self.assertEqual(
            version_string(strategy_from_rows("XAUUSD", [])),
            version_string(default_strategy("XAUUSD")),
        )

    def test_a_partial_row_set_leaves_other_expiries_at_defaults(self):
        s = strategy_from_rows("XAUUSD", [{"expiry_minutes": 15, "min_technical_score": 90}])
        self.assertEqual(s.for_expiry(15).min_technical_score, 90)
        self.assertEqual(s.for_expiry(30).min_technical_score, 78)
        self.assertEqual(s.for_expiry(60).min_technical_score, 78)

    def test_null_columns_fall_back_per_field_not_per_row(self):
        s = strategy_from_rows("XAUUSD", [
            {"expiry_minutes": 30, "min_technical_score": 85,
             "allowed_regimes": None, "allowed_sessions": None, "enabled": None},
        ])
        cfg = s.for_expiry(30)
        self.assertEqual(cfg.min_technical_score, 85)
        self.assertEqual(cfg.allowed_regimes, ALL_REGIMES)
        self.assertTrue(cfg.enabled)

    def test_unknown_expiry_rows_are_ignored_not_fatal(self):
        s = strategy_from_rows("XAUUSD", [{"expiry_minutes": 5, "min_technical_score": 10}])
        self.assertEqual(version_string(s), version_string(default_strategy("XAUUSD")))

    def test_enabled_false_survives_the_round_trip(self):
        s = strategy_from_rows("XAUUSD", [{"expiry_minutes": 60, "enabled": False}])
        self.assertFalse(s.for_expiry(60).enabled)

    def test_label_comes_from_the_stored_rows(self):
        s = strategy_from_rows("XAUUSD", [{"expiry_minutes": 15, "label": "v2-tighter-gold"}])
        self.assertTrue(version_string(s).startswith("v2-tighter-gold:"))


class ConfigValidation(unittest.TestCase):
    """Bad config should fail loudly at load time. A silently-clamped value
    would mean the stamped version describes rules that were never applied."""

    def test_rejects_unknown_regime(self):
        with self.assertRaises(ValueError):
            StrategyConfig(expiry_minutes=30, allowed_regimes=frozenset({"MOON_PHASE"}))

    def test_rejects_unknown_session(self):
        with self.assertRaises(ValueError):
            StrategyConfig(expiry_minutes=30, allowed_sessions=frozenset({"TOKYO"}))

    def test_rejects_out_of_range_score(self):
        with self.assertRaises(ValueError):
            StrategyConfig(expiry_minutes=30, min_technical_score=140)

    def test_rejects_unsupported_expiry(self):
        with self.assertRaises(ValueError):
            StrategyConfig(expiry_minutes=45)

    def test_rejects_a_strategy_missing_an_expiry(self):
        with self.assertRaises(ValueError):
            AssetStrategy(asset="XAUUSD", label="v1",
                          by_expiry={15: StrategyConfig(expiry_minutes=15)})


class LabelResolutionIsOrderIndependent(unittest.TestCase):
    """Two identical configs must never look like two rule sets because the
    rows came back in a different order."""

    def test_label_does_not_depend_on_row_order(self):
        rows = [
            {"expiry_minutes": 60, "label": "later"},
            {"expiry_minutes": 15, "label": "earlier"},
        ]
        forward = version_string(strategy_from_rows("XAUUSD", rows))
        backward = version_string(strategy_from_rows("XAUUSD", list(reversed(rows))))
        self.assertEqual(forward, backward)
        self.assertTrue(forward.startswith("earlier:"))

class WarningsLeadWithTheActualBlocker(unittest.TestCase):
    """warnings[0] is read by the dashboard cards, the analyzer's "Reason:"
    line, the admin rejected-opportunities table AND the deduplication
    fingerprint. It used to be the same standing caveat on every decision, so
    every NO_TRADE explained itself as "meta model not available" and two
    decisions blocked for different reasons deduplicated into one row.
    """

    def _blocked(self, strategy) -> str:
        history, now = _trending("XAUUSD"), datetime.now(timezone.utc)
        d = build_signal("XAUUSD", history, now=now, strategy=strategy)
        return primary_note(d.reasons, d.warnings)

    def test_first_warning_is_not_a_standing_caveat(self):
        note = self._blocked(
            AssetStrategy(asset="XAUUSD", label="v1",
                          by_expiry={e: StrategyConfig(expiry_minutes=e, min_technical_score=99)
                                     for e in (15, 30, 60)})
        )
        self.assertNotIn("Meta trade/no-trade model", note)
        self.assertNotIn("economic calendar feed", note)

    def test_different_blockers_produce_different_notes(self):
        history, now = _trending("XAUUSD"), datetime.now(timezone.utc)
        session = build_signal("XAUUSD", history, now=now).session
        by_score = self._blocked(
            AssetStrategy(asset="XAUUSD", label="v1",
                          by_expiry={e: StrategyConfig(expiry_minutes=e, min_technical_score=99)
                                     for e in (15, 30, 60)})
        )
        by_session = self._blocked(
            AssetStrategy(asset="XAUUSD", label="v1",
                          by_expiry={e: StrategyConfig(
                              expiry_minutes=e,
                              allowed_sessions=frozenset(ALL_SESSIONS - {session}))
                              for e in (15, 30, 60)})
        )
        self.assertNotEqual(by_score, by_session)
        # Truncated comparison is what dedup actually uses, so they must differ
        # inside the first 120 characters, not merely somewhere in the string.
        self.assertNotEqual(by_score[:120], by_session[:120])

    def test_standing_caveats_are_still_present_just_last(self):
        d = build_signal("XAUUSD", _trending("XAUUSD"), now=datetime.now(timezone.utc))
        self.assertTrue(any("Meta trade/no-trade model" in w for w in d.warnings))
        self.assertTrue(any("economic calendar feed" in w for w in d.warnings))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _trending(asset: str, ending_at=None) -> dict:
    base = 2400.0 if asset == "XAUUSD" else 1.1
    scale = 1.0 if asset == "XAUUSD" else 0.0004
    return {
        "M5": make_candles(300, base, 0.5 * scale, 5, ending_at=ending_at),
        "M15": make_candles(300, base, 1.5 * scale, 15, ending_at=ending_at),
        "H1": make_candles(300, base, 6.0 * scale, 60, ending_at=ending_at),
        "H4": make_candles(300, base, 24.0 * scale, 240, ending_at=ending_at),
    }


def _volatile_tail(step_minutes: int, ending_at) -> list[dict]:
    """Calm for most of the window, violent for the last twenty bars.

    Uniform wide candles do NOT produce HIGH_VOLATILITY -- ATR percentile is
    relative to the series' own history, so a constantly-wild market reads as
    perfectly normal. The regime only trips when recent range exceeds what
    came before. (The first version of this fixture got that wrong and the
    test caught it.)
    """
    calm = make_candles(280, 2400.0, 0.5, step_minutes, noise=0.2,
                        ending_at=ending_at - timedelta(minutes=step_minutes * 20))
    wild = make_candles(20, calm[-1]["close"], 0.5, step_minutes, noise=90.0,
                        ending_at=ending_at)
    return calm + wild


def _unstable(asset: str, ending_at=None) -> dict:
    """ATR spikes into the top percentile, so the regime engine classifies
    HIGH_VOLATILITY."""
    ending_at = ending_at or datetime.now(timezone.utc)
    return {
        tf: _volatile_tail(step, ending_at)
        for tf, step in (("M5", 5), ("M15", 15), ("H1", 60), ("H4", 240))
    }


if __name__ == "__main__":
    unittest.main()
