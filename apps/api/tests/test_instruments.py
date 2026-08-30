import unittest

from app.instruments import (
    SyntheticInstrumentError, assert_real_market_symbol, is_synthetic_symbol,
)


class TestSyntheticDetection(unittest.TestCase):
    def test_real_symbols_pass(self):
        for symbol in ("XAUUSD", "EURUSD", "GBPUSD", "BTCUSD", "ETHUSD", "EUR/USD", "BTC/USD"):
            self.assertFalse(is_synthetic_symbol(symbol), symbol)
            assert_real_market_symbol(symbol)  # must not raise

    def test_common_otc_spellings_are_caught(self):
        for symbol in (
            "EURUSD-OTC", "EUR/USD (OTC)", "EURUSD_otc", "EURUSD OTC",
            "otc-eurusd", "GBPUSD-Otc", "XAUUSD (otc)",
        ):
            self.assertTrue(is_synthetic_symbol(symbol), symbol)

    def test_other_synthetic_families_are_caught(self):
        for symbol in ("Volatility 75 Index", "Boom 1000 Index", "Crash 500 Index", "SYNTHETIC-EURUSD"):
            self.assertTrue(is_synthetic_symbol(symbol), symbol)

    def test_guard_raises_with_an_actionable_message(self):
        with self.assertRaises(SyntheticInstrumentError) as ctx:
            assert_real_market_symbol("EURUSD-OTC")
        message = str(ctx.exception)
        self.assertIn("EURUSD-OTC", message)
        self.assertIn("real market data only", message)

    def test_empty_symbol_is_not_flagged(self):
        # An empty/missing symbol is a different bug; this guard shouldn't
        # claim it's synthetic.
        self.assertFalse(is_synthetic_symbol(""))

    def test_does_not_false_positive_on_substrings(self):
        # 'OTC' must be a word/delimited token, not any three letters in a row.
        # These are contrived but guard against a naive `"otc" in symbol`.
        for symbol in ("BOTCOIN", "NOTCUSD"):
            self.assertFalse(is_synthetic_symbol(symbol), symbol)


if __name__ == "__main__":
    unittest.main()
