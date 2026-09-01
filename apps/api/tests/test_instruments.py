import unittest

from app.instruments import (
    REGISTRY,
    FeedDescriptor,
    FeedKind,
    FeedProvenanceError,
    Instrument,
    MarketType,
    UnknownInstrumentError,
    assert_feed_matches_instrument,
    get_instrument,
    is_crypto_symbol,
    is_otc_symbol,
    looks_synthetic,
    trades_continuously,
)

PUBLIC = FeedDescriptor("twelve_data", FeedKind.PUBLIC_MARKET)
QUOTEX = FeedDescriptor("quotex_otc", FeedKind.BROKER_OTC, broker="QUOTEX")
OTHER_BROKER = FeedDescriptor("iq_otc", FeedKind.BROKER_OTC, broker="IQOPTION")
DEMO = FeedDescriptor("demo", FeedKind.DEMO)


class TheDangerousCase(unittest.TestCase):
    """Pricing a broker-generated series with a public-market feed. The two
    are unrelated series that happen to share a name, and the resulting
    signal renders as confident and graded — identical to a real one. This
    is the single failure this module exists to prevent."""

    def test_public_market_feed_cannot_price_an_otc_instrument(self):
        with self.assertRaises(FeedProvenanceError) as ctx:
            assert_feed_matches_instrument("EURUSD_OTC", PUBLIC)
        message = str(ctx.exception)
        self.assertIn("EURUSD_OTC", message)
        self.assertIn("unrelated series", message)

    def test_otc_feed_cannot_price_a_real_instrument(self):
        """Symmetric on purpose. Quotex's EUR/USD OTC series says nothing
        about interbank EUR/USD either."""
        with self.assertRaises(FeedProvenanceError):
            assert_feed_matches_instrument("EURUSD", QUOTEX)

    def test_one_brokers_series_cannot_price_anothers(self):
        with self.assertRaises(FeedProvenanceError) as ctx:
            assert_feed_matches_instrument("EURUSD_OTC", OTHER_BROKER)
        self.assertIn("QUOTEX", str(ctx.exception))

    def test_demo_feed_is_never_valid_for_analysis(self):
        for symbol in ("EURUSD", "EURUSD_OTC"):
            with self.assertRaises(FeedProvenanceError):
                assert_feed_matches_instrument(symbol, DEMO)


class OtcIsFailClosed(unittest.TestCase):
    def test_otc_without_a_feed_descriptor_is_refused(self):
        """Unstated provenance is tolerated for real markets (it preserves
        every existing caller) but never for OTC, where provenance is the
        only thing distinguishing a real signal from a convincing fiction."""
        with self.assertRaises(FeedProvenanceError):
            assert_feed_matches_instrument("EURUSD_OTC", None)

    def test_real_market_without_a_feed_descriptor_is_allowed(self):
        self.assertEqual(assert_feed_matches_instrument("EURUSD", None).symbol, "EURUSD")

    def test_otc_with_its_own_brokers_feed_is_allowed(self):
        instrument = assert_feed_matches_instrument("EURUSD_OTC", QUOTEX)
        self.assertTrue(instrument.is_otc)
        self.assertEqual(instrument.broker, "QUOTEX")


class UnregisteredSymbols(unittest.TestCase):
    def test_unknown_symbol_is_refused_not_guessed(self):
        """Guessing is how an OTC instrument gets silently treated as a real
        one."""
        with self.assertRaises(UnknownInstrumentError):
            assert_feed_matches_instrument("EURJPY", PUBLIC)

    def test_an_otc_looking_symbol_that_was_never_registered_is_still_refused(self):
        with self.assertRaises(UnknownInstrumentError):
            assert_feed_matches_instrument("EURUSD-OTC", QUOTEX)

    def test_otc_spellings_are_recognised_even_when_unregistered(self):
        for symbol in (
            "EURUSD-OTC", "EUR/USD (OTC)", "EURUSD_otc", "EURUSD OTC",
            "otc-eurusd", "GBPUSD-Otc", "XAUUSD (otc)",
        ):
            self.assertTrue(looks_synthetic(symbol), symbol)
            self.assertTrue(is_otc_symbol(symbol), symbol)

    def test_other_synthetic_families_are_recognised(self):
        for symbol in ("Volatility 75 Index", "Boom 1000 Index", "Crash 500 Index", "SYNTHETIC-EURUSD"):
            self.assertTrue(looks_synthetic(symbol), symbol)

    def test_no_false_positives_on_substrings(self):
        """'OTC' must be a delimited token, not any three letters in a row."""
        for symbol in ("BOTCOIN", "NOTCUSD", "XAUUSD", "EURUSD", "BTCUSD"):
            self.assertFalse(looks_synthetic(symbol), symbol)

    def test_empty_symbol_is_not_flagged_as_synthetic(self):
        self.assertFalse(looks_synthetic(""))


class RegistryShape(unittest.TestCase):
    def test_every_registry_key_matches_its_instrument_symbol(self):
        for key, instrument in REGISTRY.items():
            self.assertEqual(key, instrument.symbol)

    def test_every_otc_instrument_names_its_broker(self):
        """An OTC instrument with no broker could be matched by any OTC feed,
        which defeats the cross-broker check entirely."""
        for instrument in REGISTRY.values():
            if instrument.is_otc:
                self.assertTrue(instrument.broker, f"{instrument.symbol} has no broker")

    def test_no_real_market_instrument_claims_a_broker(self):
        for instrument in REGISTRY.values():
            if not instrument.is_otc:
                self.assertIsNone(instrument.broker, instrument.symbol)

    def test_required_feed_kind_follows_market_type(self):
        self.assertIs(get_instrument("EURUSD").required_feed_kind, FeedKind.PUBLIC_MARKET)
        self.assertIs(get_instrument("EURUSD_OTC").required_feed_kind, FeedKind.BROKER_OTC)

    def test_continuous_markets_are_crypto_and_otc_only(self):
        """Forex and metals close for the weekend; crypto never does, and an
        OTC generator simply never stops."""
        for instrument in REGISTRY.values():
            if instrument.trades_continuously:
                self.assertIn(
                    instrument.market_type,
                    (MarketType.CRYPTO, MarketType.BROKER_OTC),
                    instrument.symbol,
                )

    def test_crypto_helper_still_works(self):
        self.assertTrue(is_crypto_symbol("BTCUSD"))
        self.assertFalse(is_crypto_symbol("EURUSD"))
        self.assertFalse(is_crypto_symbol("EURUSD_OTC"))

    def test_continuity_helper(self):
        self.assertTrue(trades_continuously("BTCUSD"))
        self.assertTrue(trades_continuously("EURUSD_OTC"))
        self.assertFalse(trades_continuously("EURUSD"))

    def test_registry_is_still_narrow(self):
        """Phase 30: start with one OTC instrument. Five pairs each reach a
        conclusion five times slower, and 'no pair ever reached significance'
        is the usual result of widening early. Raise this deliberately."""
        otc = [i for i in REGISTRY.values() if i.is_otc]
        self.assertLessEqual(len(otc), 3, "widen OTC coverage only once one pair has a sample size")


class InstrumentDefaults(unittest.TestCase):
    def test_a_plain_instrument_is_not_otc(self):
        i = Instrument("TESTUSD", "TEST/USD", MarketType.FOREX)
        self.assertFalse(i.is_otc)
        self.assertIsNone(i.broker)
        self.assertFalse(i.trades_continuously)


if __name__ == "__main__":
    unittest.main()
