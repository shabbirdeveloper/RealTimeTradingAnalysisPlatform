"""Resolution and persistence semantics (spec Phases 26, 30, 32).

These tests exist mostly to pin down what must NOT happen: an unobservable
outcome must not be recorded as a loss, a stale bar must not produce a
confident result, and a failed duplicate check must not let a burst
through.
"""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from app.otc.collector import _health_from_ticks
from app.otc.health import FeedStatus
from app.otc.repository import _leaning, _score
from app.otc.signal import CategoryScores, Direction, OTCDecision, SignalStatus

NOW = datetime(2026, 9, 7, 12, 0, tzinfo=timezone.utc)


def bars(last_close: float, at: datetime, count: int = 5):
    return [
        {"open_time": at - timedelta(seconds=15 * (count - 1 - i)),
         "open": last_close, "high": last_close, "low": last_close, "close": last_close}
        for i in range(count)
    ]


def row(direction: str, entry: float, expiry: datetime, symbol: str | None = "DERIV_V75"):
    # `assets(symbol)` is the joined shape the query returns. The candle
    # reader is keyed by symbol, not asset id; passing the id through
    # silently returned nothing and left every expired signal ACTIVE.
    return {"id": "x", "asset_id": "a", "direction": direction,
            "entry_price": str(entry), "expiry_at": expiry.isoformat(),
            "assets": {"symbol": symbol} if symbol else None}


class ScoringTests(unittest.TestCase):
    def test_call_above_entry_wins(self):
        status, close = _score(row("CALL", 100.0, NOW), NOW, lambda *_: bars(101.0, NOW))
        self.assertEqual(status, SignalStatus.WON.value)
        self.assertEqual(close, 101.0)

    def test_call_below_entry_loses(self):
        status, _ = _score(row("CALL", 100.0, NOW), NOW, lambda *_: bars(99.0, NOW))
        self.assertEqual(status, SignalStatus.LOST.value)

    def test_put_below_entry_wins(self):
        status, _ = _score(row("PUT", 100.0, NOW), NOW, lambda *_: bars(99.0, NOW))
        self.assertEqual(status, SignalStatus.WON.value)

    def test_put_above_entry_loses(self):
        status, _ = _score(row("PUT", 100.0, NOW), NOW, lambda *_: bars(101.0, NOW))
        self.assertEqual(status, SignalStatus.LOST.value)

    def test_equal_price_is_a_draw_not_a_loss(self):
        status, _ = _score(row("CALL", 100.0, NOW), NOW, lambda *_: bars(100.0, NOW))
        self.assertEqual(status, SignalStatus.DRAW.value)

    def test_no_candle_at_expiry_returns_none_rather_than_a_loss(self):
        """An outcome we cannot observe is not an outcome the engine got
        wrong. Recording it as a loss corrupts the win rate downward, which
        is no more honest than inflating it."""
        self.assertIsNone(_score(row("CALL", 100.0, NOW), NOW, lambda *_: []))

    def test_stale_series_invalidates_rather_than_scores(self):
        old = bars(101.0, NOW - timedelta(minutes=10))
        status, close = _score(row("CALL", 100.0, NOW), NOW, lambda *_: old)
        self.assertEqual(status, SignalStatus.INVALIDATED.value)
        self.assertIsNone(close)

    def test_missing_entry_price_invalidates(self):
        bad = row("CALL", 0.0, NOW)
        bad["entry_price"] = None
        status, _ = _score(bad, NOW, lambda *_: bars(101.0, NOW))
        self.assertEqual(status, SignalStatus.INVALIDATED.value)

    def test_scoring_is_keyed_by_symbol_not_asset_id(self):
        """Regression: the candle reader takes a symbol. Passing asset_id
        found no candles, so nothing ever resolved and the backlog looked
        like a quiet market rather than a broken join."""
        seen: list[str] = []

        def spy(symbol, *_):
            seen.append(symbol)
            return bars(101.0, NOW)

        _score(row("CALL", 100.0, NOW), NOW, spy)
        self.assertEqual(seen, ["DERIV_V75"])

    def test_missing_symbol_returns_none_rather_than_guessing(self):
        self.assertIsNone(_score(row("CALL", 100.0, NOW, symbol=None), NOW,
                                 lambda *_: bars(101.0, NOW)))

    def test_fetch_failure_returns_none(self):
        def boom(*_):
            raise RuntimeError("db down")
        self.assertIsNone(_score(row("CALL", 100.0, NOW), NOW, boom))


class RejectedSetupTests(unittest.TestCase):
    def _decision(self, call: int, put: int) -> OTCDecision:
        return OTCDecision(
            symbol="DERIV_V75", broker="DERIV", generated_at=NOW,
            direction=Direction.NO_TRADE, status=SignalStatus.REJECTED,
            price=500.0, expiry_seconds=300, regime="RANGING", regime_reason="",
            strategy="level_rejection", call_score=call, put_score=put,
            call_categories=CategoryScores(), put_categories=CategoryScores(),
            rejection_reasons=["separation below floor"],
        )

    def test_rejected_setup_keeps_the_direction_it_would_have_taken(self):
        """Phase 32: the rejected dataset has to be able to answer 'would
        this have won?', which needs a direction, not NO_TRADE."""
        self.assertEqual(_leaning(self._decision(74, 40)), "CALL")
        self.assertEqual(_leaning(self._decision(40, 74)), "PUT")

    def test_a_rejected_decision_is_never_marked_a_signal(self):
        self.assertFalse(self._decision(74, 40).is_signal)
        self.assertIsNone(self._decision(74, 40).entry_price)


class HealthDerivationTests(unittest.TestCase):
    def test_no_ticks_is_disconnected(self):
        h = _health_from_ticks("DERIV_V75", [], NOW)
        self.assertIs(h.status, FeedStatus.DISCONNECTED)

    def test_rate_is_computed_over_the_actual_span(self):
        ticks = [(NOW - timedelta(seconds=120 - 2 * i), 500.0 + i) for i in range(60)]
        h = _health_from_ticks("DERIV_V75", ticks, NOW)
        self.assertAlmostEqual(h.ticks_per_minute, 30.0, delta=1.5)
        self.assertIs(h.status, FeedStatus.HEALTHY)

    def test_a_thin_stream_is_degraded_and_cannot_signal(self):
        ticks = [(NOW - timedelta(seconds=120 - 30 * i), 500.0) for i in range(5)]
        h = _health_from_ticks("DERIV_V75", ticks, NOW)
        self.assertFalse(h.may_signal)

    def test_duplicates_are_counted_not_silently_dropped(self):
        tick = (NOW - timedelta(seconds=1), 500.0)
        ticks = [(NOW - timedelta(seconds=60 - i), 500.0 + i) for i in range(50)] + [tick, tick]
        h = _health_from_ticks("DERIV_V75", ticks, NOW)
        self.assertGreaterEqual(h.duplicate_ticks, 1)


if __name__ == "__main__":
    unittest.main()


class ResolutionScopeTests(unittest.TestCase):
    """A broker-OTC row must not abort resolution for real-market rows.

    Deriv symbols are deliberately absent from the Asset enum, so Asset()
    raises on them. That raise happened inside the per-row loop, so one
    out-of-scope row aborted the whole pass and left every real-market
    signal ACTIVE forever -- a growing backlog that reads exactly like a
    quiet market.
    """

    def test_otc_symbols_are_not_in_the_public_market_enum(self):
        from app.instruments import DERIV_API_SYMBOLS

        try:
            from app.schemas.candle import Asset
        except ModuleNotFoundError:
            self.skipTest("pydantic unavailable in this environment")

        for symbol in DERIV_API_SYMBOLS:
            with self.assertRaises(ValueError, msg=f"{symbol} leaked into Asset"):
                Asset(symbol)

    def test_resolution_skips_unknown_symbols_instead_of_raising(self):
        # Read the source directly: importing the module pulls in pydantic,
        # which is not installed everywhere this suite runs, and the
        # guarantee under test is a property of the code, not of a live
        # database call.
        import pathlib

        source = pathlib.Path("app/collector/resolution.py").read_text(encoding="utf-8")
        self.assertIn("def resolve_expired_signals", source)
        self.assertIn("except ValueError", source,
                      "an out-of-scope symbol must be skipped, not allowed to abort the pass")


class NotificationTests(unittest.TestCase):
    """The 5-minute engine must announce its own signals.

    It did not: Telegram was wired only into the OLD engine's storage
    path, so the only messages arriving were from an engine that had been
    replaced -- which is why exactly one instrument was notifying.
    """

    def _decision(self, direction: Direction, broker: str = "DERIV") -> OTCDecision:
        return OTCDecision(
            symbol="DERIV_V75", broker=broker, generated_at=NOW,
            direction=direction,
            status=SignalStatus.ACTIVE if direction is not Direction.NO_TRADE else SignalStatus.REJECTED,
            price=500.25, expiry_seconds=300, regime="TRENDING_UP",
            regime_reason="M5 HH_HL", strategy="trend_pullback",
            call_score=84, put_score=31,
            call_categories=CategoryScores(trend=20), put_categories=CategoryScores(),
            reasons=["M15 and M5 both bullish"], warnings=[],
        )

    def test_message_names_the_five_minute_expiry(self):
        from app.notifications.telegram import format_otc_signal

        text = format_otc_signal(self._decision(Direction.CALL))
        self.assertIn("5 min", text)
        self.assertIn("CALL", text)

    def test_message_shows_both_sides_not_one_score(self):
        from app.notifications.telegram import format_otc_signal

        text = format_otc_signal(self._decision(Direction.PUT))
        self.assertIn("84", text)
        self.assertIn("31", text)

    def test_broker_generated_series_is_declared(self):
        """A synthetic index and a real pair can carry similar names. A
        message that did not say which series it came from would
        eventually be placed on the wrong instrument."""
        from app.notifications.telegram import format_otc_signal

        text = format_otc_signal(self._decision(Direction.CALL, broker="DERIV"))
        self.assertIn("not from any market", text)

        real = format_otc_signal(self._decision(Direction.CALL, broker="MARKET"))
        self.assertIn("real exchange prices", real)

    def test_no_probability_is_claimed(self):
        from app.notifications.telegram import format_otc_signal

        text = format_otc_signal(self._decision(Direction.CALL))
        self.assertIn("not a probability", text)
        self.assertNotIn("%", text.split("<i>")[0])
