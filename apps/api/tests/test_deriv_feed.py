"""
The Deriv synthetic feed.

No network here. What is worth testing is the parsing and the rules --
which bars are dropped, what happens on an error, how ticks become bars --
and all of that is deterministic given a response.
"""

from __future__ import annotations

import asyncio
import unittest
from datetime import datetime, timedelta, timezone

from app.market_data.deriv_feed import (
    SUPPORTED_GRANULARITY,
    TIMEFRAME_GRANULARITY,
    DerivError,
    DerivSyntheticFeed,
    ticks_to_candles,
)
from app.market_data.errors import MarketDataError
from app.instruments import FeedKind

NOW = datetime(2026, 9, 3, 12, 0, 0, tzinfo=timezone.utc)


class StubFeed(DerivSyntheticFeed):
    """Replaces only the transport, so every rule above it is exercised."""

    def __init__(self, response: dict) -> None:
        super().__init__(app_id="test")
        self.response = response
        self.sent: dict | None = None

    def _now(self) -> datetime:
        return NOW

    async def _request(self, payload: dict) -> dict:
        self.sent = payload
        if "error" in self.response:
            err = self.response["error"]
            raise DerivError(err["code"], err["message"])
        return self.response


def candles_response(count: int, *, ending_at=NOW, granularity=60) -> dict:
    """`count` candles, the last of which is still forming."""
    out = []
    for i in range(count):
        epoch = int((ending_at - timedelta(seconds=granularity * (count - 1 - i))).timestamp())
        base = 100 + i
        out.append({"epoch": epoch, "open": base, "high": base + 1,
                    "low": base - 1, "close": base + 0.5})
    return {"msg_type": "candles", "candles": out}


def run(coro):
    return asyncio.run(coro)


class ConfigurationTests(unittest.TestCase):
    def test_an_app_id_is_required(self):
        with self.assertRaises(ValueError):
            DerivSyntheticFeed(app_id="")

    def test_the_descriptor_names_the_broker(self):
        """The provenance check compares against this. A feed that
        misreported it would defeat every downstream guarantee."""
        d = DerivSyntheticFeed(app_id="1").descriptor
        self.assertEqual(d.kind, FeedKind.BROKER_OTC)
        self.assertEqual(d.broker, "DERIV")

    def test_history_is_declared_stable(self):
        """The backtester's validity rests on closed bars not changing."""
        self.assertTrue(DerivSyntheticFeed(app_id="1").history_is_stable)

    def test_every_mapped_granularity_is_one_the_api_accepts(self):
        for tf, g in TIMEFRAME_GRANULARITY.items():
            self.assertIn(g, SUPPORTED_GRANULARITY, f"{tf} maps to an unsupported {g}s")


class BarTests(unittest.TestCase):
    def test_the_still_forming_candle_is_dropped(self):
        """The single most important rule here. Including the live candle
        corrupts every indicator and makes a backtest better informed than
        live ever was."""
        feed = StubFeed(candles_response(5))
        bars = run(feed.fetch_bars("R_75", "M1", 4))
        newest = max(b.open_time for b in bars)
        self.assertLess((NOW - newest).total_seconds(), 3600)
        self.assertLessEqual(len(bars), 4)
        # The bar whose period has not elapsed must not be among them.
        for bar in bars:
            self.assertGreaterEqual((NOW - bar.open_time).total_seconds(), 60)

    def test_it_asks_for_one_more_than_requested(self):
        """Because one will be dropped. Asking for exactly `count` returns
        one fewer closed bar than the caller asked for."""
        feed = StubFeed(candles_response(5))
        run(feed.fetch_bars("R_75", "M1", 3))
        self.assertEqual(feed.sent["count"], 4)

    def test_bars_come_back_oldest_first(self):
        feed = StubFeed(candles_response(6))
        bars = run(feed.fetch_bars("R_75", "M1", 5))
        self.assertEqual([b.open_time for b in bars], sorted(b.open_time for b in bars))

    def test_bars_carry_their_provenance(self):
        feed = StubFeed(candles_response(4))
        for bar in run(feed.fetch_bars("R_75", "M1", 3)):
            self.assertEqual(bar.source, "deriv_synthetic")
            self.assertTrue(bar.is_closed)
            self.assertEqual(bar.open_time.tzinfo, timezone.utc)

    def test_a_sub_minute_timeframe_is_refused_with_a_reason(self):
        """Deriv's finest candle is 60s. Silently returning M1 for an S15
        request would mislabel the series."""
        feed = StubFeed(candles_response(4))
        with self.assertRaises(MarketDataError) as ctx:
            run(feed.fetch_bars("R_75", "S15", 3))
        self.assertIn("60s", str(ctx.exception))

    def test_all_candles_still_forming_raises_rather_than_returning_empty(self):
        """An empty list reads as a quiet market. An error reads as no data,
        which is the truth."""
        response = {"msg_type": "candles", "candles": [
            {"epoch": int(NOW.timestamp()), "open": 1, "high": 2, "low": 0.5, "close": 1.5}
        ]}
        with self.assertRaises(MarketDataError):
            run(StubFeed(response).fetch_bars("R_75", "M1", 5))

    def test_an_api_error_carries_its_code(self):
        feed = StubFeed({"error": {"code": "InvalidSymbol", "message": "bad symbol"}})
        with self.assertRaises(DerivError) as ctx:
            run(feed.fetch_bars("NOPE", "M1", 5))
        self.assertEqual(ctx.exception.code, "InvalidSymbol")


class TickCandleTests(unittest.TestCase):
    def ticks(self, n: int, step: int = 1):
        return [(NOW - timedelta(seconds=n * step) + timedelta(seconds=i * step), 100 + (i % 5))
                for i in range(n)]

    def test_buckets_align_to_absolute_time_not_to_the_first_tick(self):
        """Aligning to arrival would make the same bar have a different
        open_time on every run, and no two runs would agree on history."""
        bars = ticks_to_candles(self.ticks(120), 15, now=NOW)
        self.assertTrue(all(int(b["open_time"].timestamp()) % 15 == 0 for b in bars))

    def test_the_forming_bucket_is_excluded(self):
        bars = ticks_to_candles(self.ticks(120), 15, now=NOW)
        for bar in bars:
            self.assertLessEqual(int(bar["open_time"].timestamp()) + 15, int(NOW.timestamp()))

    def test_ohlc_is_taken_from_the_ticks_in_order(self):
        base = datetime(2026, 9, 3, 12, 0, 0, tzinfo=timezone.utc)
        ticks = [(base, 10.0), (base + timedelta(seconds=1), 14.0),
                 (base + timedelta(seconds=2), 8.0), (base + timedelta(seconds=3), 11.0)]
        bar = ticks_to_candles(ticks, 15, now=base + timedelta(minutes=1))[0]
        self.assertEqual((bar["open"], bar["high"], bar["low"], bar["close"]), (10.0, 14.0, 8.0, 11.0))
        self.assertEqual(bar["tick_count"], 4)

    def test_out_of_order_ticks_are_sorted_before_bucketing(self):
        base = datetime(2026, 9, 3, 12, 0, 0, tzinfo=timezone.utc)
        ticks = [(base + timedelta(seconds=3), 11.0), (base, 10.0),
                 (base + timedelta(seconds=1), 14.0)]
        bar = ticks_to_candles(ticks, 15, now=base + timedelta(minutes=1))[0]
        self.assertEqual(bar["open"], 10.0)
        self.assertEqual(bar["close"], 11.0)

    def test_no_ticks_is_no_bars_not_an_error(self):
        self.assertEqual(ticks_to_candles([], 15, now=NOW), [])

    def test_a_nonsense_interval_is_rejected(self):
        with self.assertRaises(ValueError):
            ticks_to_candles(self.ticks(10), 0, now=NOW)


if __name__ == "__main__":
    unittest.main()
