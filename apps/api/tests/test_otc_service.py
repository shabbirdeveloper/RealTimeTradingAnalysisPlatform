"""
The broker-OTC collection cycle.

What is worth pinning down is the division of labour: which rungs come
from candles, which are built from ticks, and that the two together cover
the ladder the engine will ask for. Getting that wrong produces an engine
that reports insufficient history forever and reads as broken rather than
mis-wired.
"""

from __future__ import annotations

import unittest

from app.backtesting.replay import TIMEFRAME_SECONDS
from app.instruments import REGISTRY, deriv_api_symbol, get_instrument
from app.market_data.deriv_feed import (
    CANDLE_TIMEFRAMES,
    HISTORY_BARS,
    TIMEFRAME_GRANULARITY,
    TICK_TIMEFRAMES,
)

# The schema module needs pydantic, which the shipped venv has and a bare
# checkout may not. Skipping is honest here: these two assertions are about
# the enum, and the rest of the file has nothing to do with it.
try:
    from app.schemas.candle import Asset, Timeframe
    HAVE_SCHEMAS = True
except ImportError:  # pragma: no cover
    HAVE_SCHEMAS = False


class LadderCoverageTests(unittest.TestCase):
    def test_every_rung_the_engine_asks_for_is_collected(self):
        """The profile decides what build_signal reads. A rung in the
        profile that nothing collects is a permanent warm-up failure."""
        collected = set(CANDLE_TIMEFRAMES) | set(TICK_TIMEFRAMES)
        for symbol, instrument in REGISTRY.items():
            if instrument.broker != "DERIV":
                continue
            for tf in instrument.profile.timeframes:
                self.assertIn(tf, collected, f"{symbol} needs {tf}, which nothing collects")

    def test_candle_rungs_are_ones_the_api_actually_serves(self):
        for tf in CANDLE_TIMEFRAMES:
            self.assertIn(tf, TIMEFRAME_GRANULARITY, f"{tf} has no Deriv granularity")

    def test_tick_built_rungs_are_below_the_api_floor(self):
        """Anything the API can serve directly should come from the API.
        Building a minute bar from ticks when Deriv publishes one is extra
        work and a second source of truth for the same bar."""
        for tf, seconds in TICK_TIMEFRAMES.items():
            self.assertLess(seconds, 60, f"{tf} could come from candles instead")
            self.assertEqual(TIMEFRAME_SECONDS[tf], seconds)

    def test_nothing_is_collected_twice(self):
        self.assertEqual(set(CANDLE_TIMEFRAMES) & set(TICK_TIMEFRAMES), set())

    def test_history_depth_covers_the_slowest_indicator(self):
        """EMA200 plus a swing lookback. Below this the slowest indicator
        never warms and every cycle reports insufficient history."""
        self.assertGreaterEqual(HISTORY_BARS, 260)


@unittest.skipUnless(HAVE_SCHEMAS, "pydantic not installed")
class StorageBoundaryTests(unittest.TestCase):
    def test_otc_symbols_stay_out_of_the_public_market_enum(self):
        """That enum drives the public-market loop. An OTC symbol in it
        could be swept into a cycle that would price it from a quote
        vendor -- the exact confusion the provenance rules exist to stop."""
        members = {a.value for a in Asset}
        for symbol, instrument in REGISTRY.items():
            if instrument.is_otc:
                self.assertNotIn(symbol, members)

    def test_the_timeframe_enum_covers_every_collected_rung(self):
        for tf in set(CANDLE_TIMEFRAMES) | set(TICK_TIMEFRAMES):
            self.assertIn(tf, {t.value for t in Timeframe})

    def test_timeframe_enum_is_declared_shortest_first(self):
        """Postgres sorts an enum by declaration order, and the database
        type was written that way (migration 16 inserted the sub-minute
        values BEFORE M5). If these two disagree, anything ordering by
        timeframe orders differently depending on which side sorted it."""
        durations = [TIMEFRAME_SECONDS[t.value] for t in Timeframe]
        self.assertEqual(durations, sorted(durations))


class SymbolMappingTests(unittest.TestCase):
    def test_every_deriv_instrument_has_an_api_symbol(self):
        for symbol, instrument in REGISTRY.items():
            if instrument.broker == "DERIV":
                self.assertTrue(deriv_api_symbol(symbol))

    def test_a_non_deriv_symbol_is_refused_with_guidance(self):
        with self.assertRaises(KeyError) as ctx:
            deriv_api_symbol("EURUSD")
        self.assertIn("DERIV_API_SYMBOLS", str(ctx.exception))

    def test_deriv_instruments_are_continuous_and_otc(self):
        for symbol, instrument in REGISTRY.items():
            if instrument.broker == "DERIV":
                self.assertTrue(instrument.is_otc)
                self.assertTrue(instrument.trades_continuously)
                self.assertEqual(get_instrument(symbol).broker, "DERIV")


if __name__ == "__main__":
    unittest.main()
