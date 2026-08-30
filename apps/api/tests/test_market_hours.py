import unittest
from datetime import datetime, timezone

from app.collector.market_hours import any_market_open, is_market_open
from app.instruments import is_crypto_symbol

# Symbols are used directly rather than the pydantic-backed Asset enum so
# this stays runnable with no third-party packages installed.
BTCUSD, ETHUSD = "BTCUSD", "ETHUSD"
XAUUSD, EURUSD, GBPUSD = "XAUUSD", "EURUSD", "GBPUSD"
ALL_SYMBOLS = [XAUUSD, EURUSD, GBPUSD, BTCUSD, ETHUSD]

UTC = timezone.utc

# 2026-08-29 is a Saturday; 08-30 Sunday; 08-28 Friday; 08-26 Wednesday.
SATURDAY_NOON = datetime(2026, 8, 29, 12, 0, tzinfo=UTC)
SUNDAY_EARLY = datetime(2026, 8, 30, 10, 0, tzinfo=UTC)
SUNDAY_LATE = datetime(2026, 8, 30, 22, 0, tzinfo=UTC)
FRIDAY_LATE = datetime(2026, 8, 28, 23, 0, tzinfo=UTC)
WEDNESDAY_NOON = datetime(2026, 8, 26, 12, 0, tzinfo=UTC)


class TestAssetClassification(unittest.TestCase):
    def test_crypto_assets_identified(self):
        self.assertTrue(is_crypto_symbol(BTCUSD))
        self.assertTrue(is_crypto_symbol(ETHUSD))

    def test_forex_and_gold_are_not_crypto(self):
        for symbol in (XAUUSD, EURUSD, GBPUSD):
            self.assertFalse(is_crypto_symbol(symbol), symbol)


class TestCryptoNeverCloses(unittest.TestCase):
    def test_open_at_every_forex_closed_moment(self):
        for moment in (SATURDAY_NOON, SUNDAY_EARLY, FRIDAY_LATE):
            for symbol in (BTCUSD, ETHUSD):
                self.assertTrue(is_market_open(symbol, moment), f"{symbol} at {moment}")


class TestForexSchedule(unittest.TestCase):
    def test_closed_on_saturday(self):
        for symbol in (XAUUSD, EURUSD, GBPUSD):
            self.assertFalse(is_market_open(symbol, SATURDAY_NOON), symbol)

    def test_closed_sunday_before_the_open(self):
        self.assertFalse(is_market_open(EURUSD, SUNDAY_EARLY))

    def test_open_sunday_after_the_open(self):
        self.assertTrue(is_market_open(EURUSD, SUNDAY_LATE))

    def test_closed_friday_after_the_close(self):
        self.assertFalse(is_market_open(EURUSD, FRIDAY_LATE))

    def test_open_midweek(self):
        self.assertTrue(is_market_open(EURUSD, WEDNESDAY_NOON))


class TestDefaults(unittest.TestCase):
    def test_no_asset_uses_the_conservative_forex_schedule(self):
        """A caller that forgets to pass an asset must NOT get 'always open'."""
        self.assertFalse(is_market_open(None, SATURDAY_NOON))
        self.assertTrue(is_market_open(None, WEDNESDAY_NOON))


class TestAnyMarketOpen(unittest.TestCase):
    def test_true_on_a_forex_weekend_because_crypto_trades(self):
        self.assertTrue(any_market_open(SATURDAY_NOON, ALL_SYMBOLS))

    def test_false_on_a_forex_weekend_if_only_forex_is_configured(self):
        """Guards against any_market_open() hardcoding an always-open answer."""
        self.assertFalse(any_market_open(SATURDAY_NOON, [XAUUSD, EURUSD, GBPUSD]))

    def test_true_midweek(self):
        self.assertTrue(any_market_open(WEDNESDAY_NOON, ALL_SYMBOLS))


if __name__ == "__main__":
    unittest.main()
