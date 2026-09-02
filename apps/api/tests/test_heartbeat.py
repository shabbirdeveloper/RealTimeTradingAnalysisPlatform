"""
The daily report exists to make silence legible, so the things worth
testing are the claims it makes -- particularly the ones it refuses to
make when the evidence is thin.
"""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

from app.notifications.heartbeat import (
    MIN_RESOLVED_FOR_RATE,
    AssetLine,
    HeartbeatSummary,
    format_heartbeat,
)

NOW = datetime(2026, 9, 2, 0, 0, tzinfo=timezone.utc)


def summary(**kwargs) -> HeartbeatSummary:
    base = dict(window_hours=24, generated_at=NOW)
    base.update(kwargs)
    return HeartbeatSummary(**base)


class FormatTests(unittest.TestCase):
    def test_quiet_day_says_silence_is_normal(self):
        text = format_heartbeat(summary(decisions=79, signals=0, rejected=12))
        self.assertIn("Signals      0", text)
        self.assertIn("No signals is a normal result", text)

    def test_busy_day_omits_the_reassurance(self):
        text = format_heartbeat(summary(decisions=79, signals=3))
        self.assertNotIn("No signals is a normal result", text)

    def test_no_win_rate_below_the_floor(self):
        wins = MIN_RESOLVED_FOR_RATE // 2
        losses = MIN_RESOLVED_FOR_RATE - wins - 1  # one short of the floor
        text = format_heartbeat(summary(wins=wins, losses=losses))
        self.assertIn("too few to quote a rate", text)
        self.assertNotIn("%", text.split("Resolved in window")[1])

    def test_win_rate_never_appears_without_break_even(self):
        """A bare 53% reads as winning. It is not, at an 80% payout."""
        text = format_heartbeat(summary(wins=20, losses=20))
        self.assertIn("50.0%", text)
        self.assertIn("Break-even", text)

    def test_reports_zero_resolved_honestly(self):
        text = format_heartbeat(summary())
        self.assertIn("Nothing resolved yet.", text)

    def test_best_score_is_shown_against_the_bar(self):
        text = format_heartbeat(
            summary(decisions=10, best_score=44, best_asset="XAUUSD", threshold=78)
        )
        self.assertIn("Best score   44 on XAUUSD (bar is 78)", text)

    def test_stale_data_note_is_carried(self):
        text = format_heartbeat(summary(note="Stale or missing data: XAUUSD."))
        self.assertIn("Stale or missing data: XAUUSD.", text)

    def test_asset_lines_render_missing_data_without_crashing(self):
        text = format_heartbeat(
            summary(
                assets=[
                    AssetLine("XAUUSD", decisions=16, best_score=44, candle_age_minutes=7.0),
                    AssetLine("EURUSD", decisions=0, best_score=None, candle_age_minutes=None),
                ]
            )
        )
        self.assertIn("XAUUSD  16 decisions, best 44, data 7m ago", text)
        self.assertIn("EURUSD  0 decisions, best —, data no data", text)

    def test_hours_are_used_for_old_data(self):
        text = format_heartbeat(
            summary(assets=[AssetLine("XAUUSD", candle_age_minutes=185.0)])
        )
        self.assertIn("data 3.1h ago", text)

    def test_market_text_is_html_escaped(self):
        """Telegram HTML mode -- an unescaped '<' silently drops the message."""
        text = format_heartbeat(summary(note="latency < 5ms & rising"))
        self.assertIn("latency &lt; 5ms &amp; rising", text)

    def test_resolved_is_the_sum(self):
        self.assertEqual(summary(wins=3, losses=4).resolved, 7)


if __name__ == "__main__":
    unittest.main()
