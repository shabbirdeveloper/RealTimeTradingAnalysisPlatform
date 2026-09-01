import asyncio
import unittest
from datetime import datetime, timedelta, timezone

from app.instruments import FeedKind, FeedProvenanceError, assert_feed_matches_instrument
from app.market_data.otc import (
    NoOTCFeedConfigured,
    OTCBar,
    OTCFeed,
    OTCFeedNotConnected,
    get_otc_feed,
    reset_otc_feed,
    set_otc_feed,
)

NOW = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)


def run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class StubFeed(OTCFeed):
    name = "quotex_otc"
    broker = "QUOTEX"

    async def fetch_bars(self, symbol, timeframe, count):
        return [
            OTCBar(
                symbol=symbol, open_time=NOW + timedelta(minutes=i), timeframe=timeframe,
                open=1.10, high=1.11, low=1.09, close=1.105,
                is_closed=True, source=self.name,
            )
            for i in range(count)
        ]


class AbsenceIsAnErrorNotAnEmptyResult(unittest.TestCase):
    """An empty candle list would flow downstream and surface as
    'insufficient history' — which reads like a system warming up, not one
    with no data source at all."""

    def setUp(self):
        reset_otc_feed()

    def test_the_default_feed_refuses_loudly(self):
        with self.assertRaises(OTCFeedNotConnected) as ctx:
            run(get_otc_feed().fetch_bars("EURUSD_OTC", "M1", 10))
        message = str(ctx.exception)
        self.assertIn("EURUSD_OTC", message)
        self.assertIn("will not substitute", message)

    def test_the_null_feed_cannot_pass_the_provenance_check_either(self):
        """Belt and braces: even if a caller ignored the error above, the
        placeholder's descriptor names no real broker, so it still cannot
        price a Quotex instrument."""
        with self.assertRaises(FeedProvenanceError):
            assert_feed_matches_instrument("EURUSD_OTC", NoOTCFeedConfigured().descriptor)

    def test_the_null_feed_does_not_claim_stable_history(self):
        self.assertFalse(NoOTCFeedConfigured().history_is_stable)


class RegisteringAFeed(unittest.TestCase):
    def setUp(self):
        reset_otc_feed()

    def tearDown(self):
        reset_otc_feed()

    def test_a_conforming_feed_can_price_its_own_instrument(self):
        set_otc_feed(StubFeed())
        instrument = assert_feed_matches_instrument("EURUSD_OTC", get_otc_feed().descriptor)
        self.assertTrue(instrument.is_otc)

    def test_bars_come_back_closed_and_attributed(self):
        set_otc_feed(StubFeed())
        bars = run(get_otc_feed().fetch_bars("EURUSD_OTC", "S15", 3))
        self.assertEqual(len(bars), 3)
        self.assertTrue(all(b.is_closed for b in bars))
        self.assertTrue(all(b.source == "quotex_otc" for b in bars))

    def test_a_feed_that_names_no_broker_is_rejected(self):
        """The broker name is what the provenance check compares against. A
        feed without one would match any OTC instrument."""
        class Anonymous(StubFeed):
            broker = ""
        with self.assertRaises(ValueError):
            set_otc_feed(Anonymous())

    def test_a_feed_claiming_to_be_unconfigured_is_rejected(self):
        class Sneaky(StubFeed):
            broker = "NONE"
        with self.assertRaises(ValueError):
            set_otc_feed(Sneaky())

    def test_a_non_conforming_object_is_rejected(self):
        with self.assertRaises(TypeError):
            set_otc_feed(object())


class BarValidation(unittest.TestCase):
    """A malformed bar must fail at construction. Stored, it silently
    corrupts every indicator computed from it."""

    def _bar(self, **overrides):
        base = dict(
            symbol="EURUSD_OTC", open_time=NOW, timeframe="M1",
            open=1.10, high=1.11, low=1.09, close=1.105,
            is_closed=True, source="quotex_otc",
        )
        base.update(overrides)
        return OTCBar(**base)

    def test_a_valid_bar_constructs(self):
        self.assertEqual(self._bar().close, 1.105)

    def test_naive_timestamp_is_rejected(self):
        with self.assertRaises(ValueError):
            self._bar(open_time=datetime(2026, 9, 1, 12, 0))

    def test_high_below_low_is_rejected(self):
        with self.assertRaises(ValueError):
            self._bar(high=1.05, low=1.09)

    def test_close_outside_the_bar_range_is_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            self._bar(close=1.50)
        self.assertIn("outside the bar's own high/low", str(ctx.exception))

    def test_open_outside_the_bar_range_is_rejected(self):
        with self.assertRaises(ValueError):
            self._bar(open=0.90)


if __name__ == "__main__":
    unittest.main()
