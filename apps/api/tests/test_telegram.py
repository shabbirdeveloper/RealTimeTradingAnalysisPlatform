import unittest
from datetime import datetime, timezone

from app.features.signal_engine import SignalDecision
from app.notifications.telegram import TelegramNotifier, format_signal

NOW = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)


def decision(**overrides) -> SignalDecision:
    base = dict(
        asset="XAUUSD", direction="CALL", technical_score=81, grade="B",
        expiry_seconds=1800, market_regime="TRENDING_UP",
        regime_reason="H1 EMA sloping up.", entry_price=2412.55, session="LONDON",
        reasons=["H4 and H1 both bullish — trend alignment confirmed.",
                 "4/4 timeframes aligned bullish."],
        warnings=["Meta trade/no-trade model not available yet (Phase 6)."],
        timeframes=[], candidates=[], checks=[], generated_at=NOW,
    )
    base.update(overrides)
    return SignalDecision(**base)


class ConfigurationIsAllOrNothing(unittest.TestCase):
    """A token with no chat id authenticates fine and delivers nothing — a
    working-looking integration that silently drops every message."""

    def test_both_values_are_required(self):
        self.assertFalse(TelegramNotifier("token", None).is_configured)
        self.assertFalse(TelegramNotifier(None, "chat").is_configured)
        self.assertFalse(TelegramNotifier(None, None).is_configured)
        self.assertTrue(TelegramNotifier("token", "chat").is_configured)

    def test_an_unconfigured_notifier_reports_failure_rather_than_pretending(self):
        self.assertFalse(TelegramNotifier(None, None).send("hi"))


class MessageContent(unittest.TestCase):
    def test_carries_what_a_trader_needs_to_place_the_trade(self):
        text = format_signal("XAU/USD", decision())
        for expected in ("XAU/USD", "CALL", "B", "81/100", "30m", "2412.55"):
            self.assertIn(expected, text, expected)

    def test_states_that_there_is_no_calibrated_confidence(self):
        """Omitting this would make the message read as more certain than the
        system is. The grade is capped at B for a reason."""
        text = format_signal("XAU/USD", decision())
        self.assertIn("no calibrated ML confidence", text)

    def test_warns_against_placing_a_real_market_signal_on_an_otc_pair(self):
        text = format_signal("EUR/USD", decision())
        self.assertIn("OTC", text)

    def test_the_otc_warning_is_dropped_for_an_actual_otc_instrument(self):
        """Telling someone not to trade OTC on an OTC signal is nonsense, and
        a warning that is obviously wrong teaches people to skip warnings."""
        text = format_signal("EUR/USD (OTC)", decision(), is_otc=True)
        self.assertNotIn("Do NOT place this on a broker", text)

    def test_says_the_platform_does_not_trade_for_you(self):
        self.assertIn("never trades for you", format_signal("XAU/USD", decision()))

    def test_market_text_is_escaped(self):
        """Unescaped angle brackets break Telegram HTML parsing, and a broken
        message is a missed signal."""
        text = format_signal("A<b>B", decision(reasons=["EMA20 > EMA50 & rising"]))
        self.assertIn("A&lt;b&gt;B", text)
        self.assertIn("&amp;", text)
        self.assertNotIn("EMA20 > EMA50", text)

    def test_a_put_reads_as_a_put(self):
        text = format_signal("XAU/USD", decision(direction="PUT"))
        self.assertIn("PUT", text)
        self.assertNotIn("CALL", text)

    def test_a_missing_expiry_does_not_render_as_a_number(self):
        self.assertIn("—", format_signal("XAU/USD", decision(expiry_seconds=None)))

    def test_sub_minute_expiries_read_in_seconds(self):
        text = format_signal("EUR/USD (OTC)", decision(expiry_seconds=30), is_otc=True)
        self.assertIn("30s", text)


if __name__ == "__main__":
    unittest.main()
