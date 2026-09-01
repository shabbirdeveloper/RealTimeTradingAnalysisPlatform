import unittest
from datetime import datetime, timedelta, timezone

from app.backtesting.engine import run_backtest, _score_bucket
from app.backtesting import replay

UTC = timezone.utc
END = datetime(2026, 8, 24, 0, 0, tzinfo=UTC)


def series_ending_at(as_of, count, step_minutes, price, drift, future_bars=0, wobble=1.0):
    out = []
    p = price
    first_open = as_of - timedelta(minutes=step_minutes * count)
    for i in range(count + future_bars):
        open_time = first_open + timedelta(minutes=step_minutes * i)
        out.append({
            "open_time": open_time, "open": p,
            "high": p + wobble, "low": p - wobble, "close": p + drift,
        })
        p += drift
    return out


def uptrend_history(future_bars=200):
    return {
        "H4": series_ending_at(END, 260, 240, 2000.0, 3.0, future_bars=future_bars // 48 + 2),
        "H1": series_ending_at(END, 260, 60, 2000.0, 1.0, future_bars=future_bars // 12 + 2),
        "M15": series_ending_at(END, 260, 15, 2000.0, 0.4, future_bars=future_bars // 3 + 2),
        "M5": series_ending_at(END, 260, 5, 2000.0, 0.2, future_bars=future_bars),
    }


class TestRunBacktest(unittest.TestCase):
    def test_empty_history_is_reported_not_crashed(self):
        summary = run_backtest(
            {"XAUUSD": {"M5": [], "M15": [], "H1": [], "H4": []}},
            start=END - timedelta(hours=2), end=END, technical_score_threshold=78,
        )
        self.assertEqual(summary.total_opportunities, 0)
        self.assertTrue(any("no M5 candle history" in n for n in summary.notes))

    def test_window_with_no_candles_is_reported(self):
        summary = run_backtest(
            {"XAUUSD": uptrend_history()},
            start=datetime(2020, 1, 1, tzinfo=UTC), end=datetime(2020, 1, 2, tzinfo=UTC),
            technical_score_threshold=78,
        )
        self.assertEqual(summary.total_opportunities, 0)
        self.assertTrue(any("no M5 candles inside the requested window" in n for n in summary.notes))

    def test_sustained_uptrend_produces_resolved_winning_calls(self):
        summary = run_backtest(
            {"XAUUSD": uptrend_history()},
            start=END - timedelta(hours=3), end=END,
            technical_score_threshold=78, step_minutes=15,
        )
        self.assertGreater(summary.accepted_signals, 0)
        # In a monotonic uptrend, every resolved CALL must win. If any lost,
        # entry/exit pricing is wired up wrong.
        self.assertGreater(summary.wins, 0)
        self.assertEqual(summary.losses, 0)
        self.assertEqual(summary.win_rate, 100.0)
        for o in summary.opportunities:
            self.assertEqual(o.direction, "CALL")

    def test_accuracy_is_zero_and_flagged_when_nothing_resolves(self):
        # History stops at END, and the window sits right at that edge, so
        # every signal's expiry falls past the last stored candle. Nothing
        # can be resolved honestly -- the engine must say so, not guess.
        history = uptrend_history(future_bars=0)
        summary = run_backtest(
            {"XAUUSD": history}, start=END - timedelta(minutes=10), end=END,
            technical_score_threshold=78, step_minutes=5,
        )
        self.assertEqual(summary.wins, 0)
        self.assertEqual(summary.losses, 0)
        self.assertEqual(summary.accuracy, 0.0)
        self.assertGreater(summary.unresolved, 0)
        self.assertTrue(any("unresolved rather than guessed" in n for n in summary.notes))

    def test_threshold_sweep_changes_accepted_vs_rejected_split(self):
        history = uptrend_history()
        window = {"start": END - timedelta(hours=3), "end": END}
        lenient = run_backtest({"XAUUSD": history}, **window, technical_score_threshold=50, step_minutes=15)
        strict = run_backtest({"XAUUSD": history}, **window, technical_score_threshold=99, step_minutes=15)
        self.assertGreater(lenient.accepted_signals, strict.accepted_signals)
        self.assertEqual(strict.accepted_signals, 0)
        self.assertGreater(strict.rejected_signals, 0)
        self.assertEqual(strict.signal_coverage, 0.0)

    def test_expiry_filter_restricts_results(self):
        history = uptrend_history()
        summary = run_backtest(
            {"XAUUSD": history}, start=END - timedelta(hours=3), end=END,
            technical_score_threshold=78, expiry_filter=60, step_minutes=15,
        )
        for o in summary.opportunities:
            self.assertEqual(o.expiry_seconds, 60)

    def test_regime_filter_restricts_results(self):
        history = uptrend_history()
        summary = run_backtest(
            {"XAUUSD": history}, start=END - timedelta(hours=3), end=END,
            technical_score_threshold=78, regime_filter="RANGING", step_minutes=15,
        )
        # The fixture is a clean uptrend, so a RANGING filter must exclude everything.
        self.assertEqual(summary.total_opportunities, 0)

    def test_decision_points_never_use_unclosed_candles(self):
        """End-to-end guard: every recorded entry price must equal the close
        of an M5 candle that had actually closed at that decision time."""
        history = uptrend_history()
        summary = run_backtest(
            {"XAUUSD": history}, start=END - timedelta(hours=2), end=END,
            technical_score_threshold=78, step_minutes=5,
        )
        self.assertGreater(len(summary.opportunities), 0)
        for o in summary.opportunities:
            closed = replay.candles_closed_by(history["M5"], "M5", o.generated_at)
            self.assertEqual(o.entry_price, float(closed[-1]["close"]))

    def test_breakdowns_cover_accepted_signals(self):
        summary = run_backtest(
            {"XAUUSD": uptrend_history()}, start=END - timedelta(hours=3), end=END,
            technical_score_threshold=78, step_minutes=15,
        )
        total_in_buckets = sum(b["signals"] for b in summary.performance_by_pair)
        self.assertEqual(total_in_buckets, summary.accepted_signals)
        self.assertEqual(
            sum(b["signals"] for b in summary.performance_by_regime), summary.accepted_signals
        )


class TestScoreBucket(unittest.TestCase):
    def test_buckets(self):
        self.assertEqual(_score_bucket(95), "90-99")
        self.assertEqual(_score_bucket(80), "80-89")
        self.assertEqual(_score_bucket(70), "70-79")
        self.assertEqual(_score_bucket(60), "60-69")
        self.assertEqual(_score_bucket(10), "<60")


if __name__ == "__main__":
    unittest.main()
