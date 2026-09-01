import unittest
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from app.backtesting.replay import ReplayError, candles_closed_by
from app.market_data.closed_bars import split_closed

NOW = datetime(2026, 8, 31, 10, 7, 0, tzinfo=timezone.utc)


@dataclass
class Bar:
    """Stands in for schemas.candle.Candle -- the filter only needs
    .open_time, which is deliberate: it must work on whatever a provider
    returns without dragging the storage schema into it."""

    open_time: datetime


def bars(*minutes_ago: int) -> list[Bar]:
    """Oldest-first, which is the contract every caller and the replay module
    share. Sorted here rather than trusting the argument order: an earlier
    version of this helper returned newest-first and the linear scan it was
    written against silently tolerated it."""
    return [Bar(NOW - timedelta(minutes=m)) for m in sorted(minutes_ago, reverse=True)]


class TheFormingBarIsRejected(unittest.TestCase):
    def test_a_bar_whose_window_has_not_ended_is_not_closed(self):
        # 10:05 on a 5-minute feed, read at 10:07: two minutes of a
        # five-minute window. This is the bar the whole module exists for.
        split = split_closed(bars(15, 10, 5, 2), "M5", NOW)
        self.assertEqual(len(split.closed), 3)
        self.assertEqual(len(split.forming), 1)
        self.assertEqual(split.forming[0].open_time, NOW - timedelta(minutes=2))

    def test_a_bar_closing_exactly_now_is_closed(self):
        """The boundary is inclusive: at 10:10 the 10:05 bar is finished.
        Excluding it would leave the newest bar permanently one poll behind."""
        split = split_closed(bars(5), "M5", NOW)
        self.assertEqual(len(split.closed), 1)
        self.assertEqual(split.forming, [])

    def test_one_second_before_the_boundary_it_is_not_closed(self):
        split = split_closed(bars(5), "M5", NOW - timedelta(seconds=1))
        self.assertEqual(split.closed, [])
        self.assertEqual(len(split.forming), 1)

    def test_all_bars_forming_yields_nothing_rather_than_a_best_effort(self):
        split = split_closed(bars(1), "M5", NOW)
        self.assertEqual(split.closed, [])
        self.assertEqual(len(split.forming), 1)

    def test_empty_input_is_not_an_error(self):
        split = split_closed([], "M5", NOW)
        self.assertEqual((split.closed, split.forming, split.future), ([], [], []))

    def test_longer_timeframes_use_their_own_window(self):
        """An H4 bar opening 3 hours ago is still forming; the same open_time
        on an M5 feed closed long ago. Getting this wrong on the slow
        timeframes is the most damaging version of the bug -- it leaks up to
        four hours of future price."""
        four_hours = bars(180)
        self.assertEqual(len(split_closed(four_hours, "M5", NOW).closed), 1)
        self.assertEqual(len(split_closed(four_hours, "H4", NOW).closed), 0)
        self.assertEqual(len(split_closed(four_hours, "H4", NOW).forming), 1)


class ImpossibleBarsAreSeparatedFromRoutineOnes(unittest.TestCase):
    """A bar opening in the future is not a partial bar -- it cannot exist.
    Filing it under `forming` would hide a clock or timezone fault inside a
    counter expected to sit at 1."""

    def test_future_bars_are_reported_separately(self):
        split = split_closed([Bar(NOW + timedelta(minutes=5))], "M5", NOW)
        self.assertEqual(split.closed, [])
        self.assertEqual(split.forming, [])
        self.assertEqual(len(split.future), 1)

    def test_future_bars_are_never_stored(self):
        split = split_closed(bars(10) + [Bar(NOW + timedelta(hours=1))], "M5", NOW)
        self.assertEqual(len(split.closed), 1)
        self.assertEqual(split.dropped, 1)


class MatchesTheBacktestersDefinition(unittest.TestCase):
    """The point of FIN-04 is that live and replay must agree on what was
    knowable. Two definitions of 'closed' that drift apart IS the bug, so
    this asserts they agree rather than trusting the shared import."""

    def test_same_verdict_as_replay_across_a_whole_window(self):
        series = bars(*range(0, 60, 5))
        as_dicts = [{"open_time": b.open_time} for b in series]
        for timeframe in ("M5", "M15", "H1", "H4"):
            mine = {b.open_time for b in split_closed(series, timeframe, NOW).closed}
            theirs = {c["open_time"] for c in candles_closed_by(as_dicts, timeframe, NOW)}
            self.assertEqual(mine, theirs, f"disagreement on {timeframe}")


class RefusesAmbiguousInput(unittest.TestCase):
    """Naive datetimes are how a timezone bug becomes a silent one."""

    def test_naive_now_is_rejected(self):
        with self.assertRaises(ReplayError):
            split_closed(bars(10), "M5", datetime(2026, 8, 31, 10, 7))

    def test_naive_candle_time_is_rejected(self):
        with self.assertRaises(ReplayError):
            split_closed([Bar(datetime(2026, 8, 31, 9, 0))], "M5", NOW)

    def test_unknown_timeframe_is_rejected(self):
        with self.assertRaises(ReplayError):
            split_closed(bars(10), "M7", NOW)


if __name__ == "__main__":
    unittest.main()
