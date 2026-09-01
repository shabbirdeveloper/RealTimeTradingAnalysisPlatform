import unittest
from datetime import datetime, timedelta, timezone

from app.backtesting import replay
from app.features.signal_engine import build_signal


UTC = timezone.utc


def candle(open_time: datetime, o=100.0, h=101.0, l=99.0, c=100.5) -> dict:
    return {"open_time": open_time, "open": o, "high": h, "low": l, "close": c}


def series(start: datetime, count: int, step_minutes: int, price=100.0, drift=0.0) -> list[dict]:
    out = []
    p = price
    for i in range(count):
        out.append(candle(start + timedelta(minutes=step_minutes * i), o=p, h=p + 1, l=p - 1, c=p + drift))
        p += drift
    return out


class TestCandleCloseTime(unittest.TestCase):
    def test_close_time_is_open_plus_duration(self):
        t = datetime(2026, 8, 24, 12, 0, tzinfo=UTC)
        self.assertEqual(replay.candle_close_time(candle(t), "M5"), t + timedelta(minutes=5))
        self.assertEqual(replay.candle_close_time(candle(t), "H4"), t + timedelta(minutes=240))

    def test_sub_minute_timeframes_are_supported(self):
        """Broker-OTC instruments are traded on 15s-1m horizons. These were
        unrepresentable while durations were integer minutes -- 15 seconds is
        not an integer number of minutes -- so the no-look-ahead rule could
        not be applied to them at all."""
        t = datetime(2026, 8, 24, 12, 0, tzinfo=UTC)
        self.assertEqual(replay.candle_close_time(candle(t), "S15"), t + timedelta(seconds=15))
        self.assertEqual(replay.candle_close_time(candle(t), "S30"), t + timedelta(seconds=30))
        self.assertEqual(replay.candle_close_time(candle(t), "M1"), t + timedelta(minutes=1))
        self.assertEqual(replay.candle_close_time(candle(t), "M3"), t + timedelta(minutes=3))

    def test_sub_minute_look_ahead_rule_still_holds(self):
        """The whole guarantee, at 15-second resolution: a bar that opened
        10 seconds ago has not closed and must not be visible."""
        t = datetime(2026, 8, 24, 12, 0, 0, tzinfo=UTC)
        bars = [candle(t), candle(t + timedelta(seconds=15)), candle(t + timedelta(seconds=30))]
        as_of = t + timedelta(seconds=40)
        visible = replay.candles_closed_by(bars, "S15", as_of)
        self.assertEqual([c["open_time"] for c in visible],
                         [t, t + timedelta(seconds=15)])

    def test_unknown_timeframe_raises(self):
        t = datetime(2026, 8, 24, 12, 0, tzinfo=UTC)
        with self.assertRaises(replay.ReplayError):
            replay.candle_close_time(candle(t), "M7")

    def test_naive_datetime_raises(self):
        naive = datetime(2026, 8, 24, 12, 0)
        with self.assertRaises(replay.ReplayError):
            replay.candle_close_time(candle(naive), "M5")


class TestCandlesClosedBy(unittest.TestCase):
    def test_excludes_a_candle_that_has_not_closed_yet(self):
        t = datetime(2026, 8, 24, 12, 0, tzinfo=UTC)
        candles = [candle(t)]
        # One second before its close, this candle is not yet knowable.
        just_before = t + timedelta(minutes=5) - timedelta(seconds=1)
        self.assertEqual(replay.candles_closed_by(candles, "M5", just_before), [])
        # Exactly at close, it is.
        self.assertEqual(len(replay.candles_closed_by(candles, "M5", t + timedelta(minutes=5))), 1)

    def test_h4_candle_is_not_visible_an_hour_into_its_window(self):
        # This is the case that would silently leak the most future data:
        # an H4 bar opening at 12:00 is not knowable at 13:00.
        t = datetime(2026, 8, 24, 12, 0, tzinfo=UTC)
        candles = [candle(t)]
        self.assertEqual(replay.candles_closed_by(candles, "H4", datetime(2026, 8, 24, 13, 0, tzinfo=UTC)), [])
        self.assertEqual(len(replay.candles_closed_by(candles, "H4", datetime(2026, 8, 24, 16, 0, tzinfo=UTC))), 1)

    def test_does_not_mutate_input(self):
        t = datetime(2026, 8, 24, 12, 0, tzinfo=UTC)
        candles = series(t, 10, 5)
        original_length = len(candles)
        replay.candles_closed_by(candles, "M5", t + timedelta(minutes=20))
        self.assertEqual(len(candles), original_length)

    def test_returns_oldest_first_prefix(self):
        t = datetime(2026, 8, 24, 12, 0, tzinfo=UTC)
        candles = series(t, 10, 5)
        got = replay.candles_closed_by(candles, "M5", t + timedelta(minutes=25))
        self.assertEqual([c["open_time"] for c in got], [c["open_time"] for c in candles[:5]])


class TestSliceHistory(unittest.TestCase):
    def test_slices_every_timeframe_by_its_own_duration(self):
        t = datetime(2026, 8, 24, 8, 0, tzinfo=UTC)
        history = {
            "M5": series(t, 24, 5),    # covers 08:00 -> 10:00
            "H1": series(t, 2, 60),    # 08:00, 09:00
            "H4": series(t, 1, 240),   # 08:00 (closes 12:00)
        }
        as_of = datetime(2026, 8, 24, 10, 0, tzinfo=UTC)
        sliced = replay.slice_history(history, as_of)
        self.assertEqual(len(sliced["M5"]), 24)   # all closed by 10:00
        self.assertEqual(len(sliced["H1"]), 2)    # both closed (09:00 closes at 10:00)
        self.assertEqual(len(sliced["H4"]), 0)    # doesn't close until 12:00


class TestFirstCandleAtOrAfter(unittest.TestCase):
    def test_finds_the_expiry_candle(self):
        t = datetime(2026, 8, 24, 12, 0, tzinfo=UTC)
        candles = series(t, 12, 5)
        found = replay.first_candle_at_or_after(candles, datetime(2026, 8, 24, 12, 30, tzinfo=UTC))
        self.assertIsNotNone(found)
        self.assertEqual(found["open_time"], datetime(2026, 8, 24, 12, 30, tzinfo=UTC))

    def test_returns_none_past_end_of_history(self):
        t = datetime(2026, 8, 24, 12, 0, tzinfo=UTC)
        candles = series(t, 12, 5)
        self.assertIsNone(replay.first_candle_at_or_after(candles, datetime(2026, 8, 25, tzinfo=UTC)))


AS_OF = datetime(2026, 8, 24, 0, 0, tzinfo=UTC)


def series_ending_at(as_of: datetime, count: int, step_minutes: int, price: float, drift: float,
                     future_bars: int = 0) -> list[dict]:
    """`count` bars all fully CLOSED by `as_of` (the last one closing exactly
    at `as_of`), optionally followed by `future_bars` that close after it.
    Built this way so a slice at `as_of` has enough history on every
    timeframe for the signal engine to produce a real, fully-analyzed
    decision -- otherwise a look-ahead test passes trivially by
    short-circuiting on insufficient data.
    """
    out = []
    p = price
    first_open = as_of - timedelta(minutes=step_minutes * count)
    for i in range(count + future_bars):
        open_time = first_open + timedelta(minutes=step_minutes * i)
        out.append({"open_time": open_time, "open": p, "high": p + 1, "low": p - 1, "close": p + drift})
        p += drift
    return out


class TestNoLookAheadBias(unittest.TestCase):
    """The headline correctness property of the whole backtester."""

    def _history(self) -> dict[str, list[dict]]:
        # A clean, sustained uptrend, sized so that at AS_OF every timeframe
        # has 260 closed bars -- enough for EMA200 and a real regime read.
        return {
            "H4": series_ending_at(AS_OF, 260, 240, 2000.0, 3.0, future_bars=10),
            "H1": series_ending_at(AS_OF, 260, 60, 2000.0, 1.0, future_bars=10),
            "M15": series_ending_at(AS_OF, 260, 15, 2000.0, 0.4, future_bars=10),
            "M5": series_ending_at(AS_OF, 260, 5, 2000.0, 0.2, future_bars=10),
        }

    def test_fixture_produces_a_real_accepted_signal(self):
        """Guards the tests below from passing trivially. If the engine bailed
        early on insufficient data, a corrupted future couldn't change the
        outcome for entirely uninteresting reasons -- so assert the full
        analysis path actually ran and produced a directional signal."""
        decision = build_signal("XAUUSD", replay.slice_history(self._history(), AS_OF), now=AS_OF)
        for tf in decision.timeframes:
            self.assertFalse(tf.insufficient_data, f"{tf.timeframe} had insufficient data")
        self.assertEqual(decision.direction, "CALL")
        self.assertEqual(decision.market_regime, "TRENDING_UP")
        self.assertGreater(decision.technical_score, 0)
        self.assertEqual(len(decision.candidates), 3)
        # Even on a textbook-clean trend, no calibrated model exists, so the
        # grade must still be capped at B (spec section 10).
        self.assertEqual(decision.grade, "B")

    def test_future_price_spike_cannot_change_an_earlier_decision(self):
        as_of = AS_OF

        clean = self._history()
        decision_clean = build_signal("XAUUSD", replay.slice_history(clean, as_of), now=as_of)

        # Now violently corrupt everything AFTER as_of. A backtester with
        # look-ahead bias would produce a different decision; a correct one
        # cannot even see these bars.
        spiked = self._history()
        for timeframe, candles in spiked.items():
            for c in candles:
                if replay.candle_close_time(c, timeframe) > as_of:
                    c["open"] = c["high"] = c["low"] = c["close"] = 999999.0
        decision_spiked = build_signal("XAUUSD", replay.slice_history(spiked, as_of), now=as_of)

        self.assertEqual(decision_clean.direction, decision_spiked.direction)
        self.assertEqual(decision_clean.technical_score, decision_spiked.technical_score)
        self.assertEqual(decision_clean.market_regime, decision_spiked.market_regime)
        self.assertEqual(decision_clean.expiry_seconds, decision_spiked.expiry_seconds)
        self.assertEqual(decision_clean.grade, decision_spiked.grade)
        self.assertEqual(decision_clean.entry_price, decision_spiked.entry_price)
        self.assertEqual(
            [(c.expiry_seconds, c.technical_score) for c in decision_clean.candidates],
            [(c.expiry_seconds, c.technical_score) for c in decision_spiked.candidates],
        )
        self.assertEqual(
            [(t.timeframe, t.bias, t.strength) for t in decision_clean.timeframes],
            [(t.timeframe, t.bias, t.strength) for t in decision_spiked.timeframes],
        )

    def test_slice_never_includes_a_candle_closing_after_as_of(self):
        as_of = AS_OF - timedelta(minutes=37)  # deliberately off-boundary
        sliced = replay.slice_history(self._history(), as_of)
        for timeframe, candles in sliced.items():
            for c in candles:
                self.assertLessEqual(
                    replay.candle_close_time(c, timeframe), as_of,
                    f"{timeframe} candle at {c['open_time']} had not closed by {as_of}",
                )


if __name__ == "__main__":
    unittest.main()
