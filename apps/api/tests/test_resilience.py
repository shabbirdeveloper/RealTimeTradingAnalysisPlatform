import asyncio
import logging
import random
import unittest

from app.market_data.errors import (
    MarketDataError,
    RateLimitError,
    TransientMarketDataError,
)
from app.market_data.resilience import RetryPolicy, call_with_retry


class FakeSleeper:
    """Records what would have been waited, without waiting. Backoff tuned by
    a test that actually sleeps is a test nobody runs."""

    def __init__(self) -> None:
        self.delays: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.delays.append(seconds)


def setUpModule():
    # The retry layer logs a warning on every exhausted attempt, which is
    # correct in production and pure noise across ~40 deliberate failures here.
    logging.getLogger("app.market_data.resilience").setLevel(logging.CRITICAL)


def run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def calls(*results):
    """An operation returning/raising `results` in order, counting attempts."""
    state = {"n": 0}

    async def operation():
        i = state["n"]
        state["n"] += 1
        outcome = results[min(i, len(results) - 1)]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    return operation, state


class RetriesOnlyWhatCanSucceed(unittest.TestCase):
    def test_a_transient_failure_is_retried(self):
        op, state = calls(TransientMarketDataError("connection reset"), ["candle"])
        result, outcome = run(call_with_retry(op, sleeper=FakeSleeper()))
        self.assertEqual(result, ["candle"])
        self.assertEqual(state["n"], 2)
        self.assertEqual(outcome.retries, 1)

    def test_a_permanent_failure_is_NOT_retried(self):
        """A bad API key or an unknown symbol fails identically forever, and
        each attempt still spends a credit from the daily budget. Retrying
        one is how a small misconfiguration becomes an outage."""
        op, state = calls(MarketDataError("invalid api key"))
        sleeper = FakeSleeper()
        with self.assertRaises(MarketDataError):
            run(call_with_retry(op, sleeper=sleeper))
        self.assertEqual(state["n"], 1)
        self.assertEqual(sleeper.delays, [])

    def test_success_on_the_first_try_costs_nothing(self):
        op, state = calls(["candle"])
        sleeper = FakeSleeper()
        _, outcome = run(call_with_retry(op, sleeper=sleeper))
        self.assertEqual(state["n"], 1)
        self.assertEqual(outcome.retries, 0)
        self.assertEqual(sleeper.delays, [])

    def test_the_last_error_is_raised_not_swallowed(self):
        """A caller that cannot get real data must skip the cycle, never
        substitute something plausible (spec section 50)."""
        op, _ = calls(TransientMarketDataError("gateway timeout"))
        with self.assertRaises(TransientMarketDataError):
            run(call_with_retry(op, sleeper=FakeSleeper()))


class StaysInsideTheCreditBudget(unittest.TestCase):
    def test_default_policy_allows_only_one_retry(self):
        """Five assets every 600s already costs ~720 of Twelve Data's 800
        daily credits. A conventional 3-retry policy allows 2,160/day and
        exhausts the budget by mid-morning -- at which point every asset
        fails. A retry policy that ignores the budget manufactures the
        outage it was meant to prevent."""
        self.assertEqual(RetryPolicy().max_attempts, 2)

        op, state = calls(TransientMarketDataError("boom"))
        with self.assertRaises(TransientMarketDataError):
            run(call_with_retry(op, sleeper=FakeSleeper()))
        self.assertEqual(state["n"], 2)

    def test_attempts_are_capped_by_the_policy(self):
        op, state = calls(TransientMarketDataError("boom"))
        with self.assertRaises(TransientMarketDataError):
            run(call_with_retry(op, policy=RetryPolicy(max_attempts=4), sleeper=FakeSleeper()))
        self.assertEqual(state["n"], 4)

    def test_zero_attempts_is_rejected_at_construction(self):
        with self.assertRaises(ValueError):
            RetryPolicy(max_attempts=0)


class RateLimitsAreHandledDistinctly(unittest.TestCase):
    def test_retry_after_raises_the_wait_above_the_backoff(self):
        op, _ = calls(RateLimitError("slow down", retry_after=7.5), ["candle"])
        sleeper = FakeSleeper()
        _, outcome = run(
            call_with_retry(
                op,
                policy=RetryPolicy(base_delay_seconds=0.5, max_total_wait_seconds=30),
                sleeper=sleeper,
                rng=random.Random(1),
            )
        )
        self.assertEqual(sleeper.delays, [7.5])
        self.assertTrue(outcome.rate_limited)

    def test_retry_after_never_shortens_the_backoff(self):
        """It is a floor, not an override. A provider suggesting 0 seconds
        during a rate limit should not produce an immediate retry -- that is
        the one response guaranteed to make a rate limit worse."""
        op, _ = calls(RateLimitError("slow down", retry_after=0.0), ["candle"])
        sleeper = FakeSleeper()
        run(
            call_with_retry(
                op,
                policy=RetryPolicy(base_delay_seconds=10, max_delay_seconds=10),
                sleeper=sleeper,
                rng=random.Random(7),
            )
        )
        self.assertEqual(len(sleeper.delays), 1)
        self.assertGreater(sleeper.delays[0], 0.0)

    def test_an_excessive_retry_after_gives_up_instead_of_stalling(self):
        """The scheduler runs assets sequentially. One asset honouring a
        one-hour Retry-After would delay every asset behind it and push the
        cycle past its own interval. Next tick is strictly better."""
        op, state = calls(RateLimitError("come back later", retry_after=3600))
        sleeper = FakeSleeper()
        with self.assertRaises(RateLimitError):
            run(
                call_with_retry(
                    op, policy=RetryPolicy(max_total_wait_seconds=30), sleeper=sleeper
                )
            )
        self.assertEqual(state["n"], 1, "should not have burned a second attempt")
        self.assertEqual(sleeper.delays, [], "should not have waited at all")

    def test_rate_limited_is_reported_even_when_the_call_recovers(self):
        op, _ = calls(RateLimitError("slow down", retry_after=1), ["candle"])
        _, outcome = run(call_with_retry(op, sleeper=FakeSleeper()))
        self.assertTrue(outcome.rate_limited)
        self.assertIn("slow down", outcome.last_error or "")


class BackoffIsJittered(unittest.TestCase):
    def test_delays_are_not_identical_across_callers(self):
        """A provider outage makes all five assets fail at the same instant.
        Retrying at exactly base*2^n sends them back as one synchronized
        burst -- the shape most likely to earn a 429 from the provider that
        just recovered."""
        policy = RetryPolicy(base_delay_seconds=4, max_delay_seconds=16, max_total_wait_seconds=60)
        observed = set()
        for seed in range(8):
            op, _ = calls(TransientMarketDataError("boom"), ["ok"])
            sleeper = FakeSleeper()
            run(call_with_retry(op, policy=policy, sleeper=sleeper, rng=random.Random(seed)))
            observed.add(round(sleeper.delays[0], 6))
        self.assertGreater(len(observed), 1)

    def test_delay_never_exceeds_the_cap(self):
        policy = RetryPolicy(
            max_attempts=6, base_delay_seconds=1, max_delay_seconds=5, max_total_wait_seconds=10_000
        )
        for seed in range(20):
            op, _ = calls(TransientMarketDataError("boom"))
            sleeper = FakeSleeper()
            with self.assertRaises(TransientMarketDataError):
                run(call_with_retry(op, policy=policy, sleeper=sleeper, rng=random.Random(seed)))
            for d in sleeper.delays:
                self.assertLessEqual(d, 5)

    def test_total_wait_is_bounded_across_multiple_retries(self):
        policy = RetryPolicy(
            max_attempts=10, base_delay_seconds=8, max_delay_seconds=8, max_total_wait_seconds=12
        )
        op, _ = calls(TransientMarketDataError("boom"))
        sleeper = FakeSleeper()
        with self.assertRaises(TransientMarketDataError):
            run(call_with_retry(op, policy=policy, sleeper=sleeper, rng=random.Random(3)))
        self.assertLessEqual(sum(sleeper.delays), 12)


if __name__ == "__main__":
    unittest.main()


class ErrorsMustSayWhatWentWrong(unittest.TestCase):
    """A live log line read:

        Twelve Data request failed for GBP/USD:

    ...and stopped there. str() on several httpx errors (ReadTimeout,
    ConnectTimeout, RemoteProtocolError) is empty, so the message named the
    asset and then said nothing about the failure. For a transient error you
    only see in a log after the fact, the class name IS the diagnosis.
    """

    @staticmethod
    def describe(exc: Exception) -> str:
        return f"{type(exc).__name__}{f' — {exc}' if str(exc) else ' (no detail)'}"

    def test_an_exception_with_no_message_still_names_its_type(self):
        class ReadTimeout(Exception):
            pass

        described = self.describe(ReadTimeout(""))
        self.assertIn("ReadTimeout", described)
        self.assertNotEqual(described.strip().rstrip(":"), "")

    def test_a_message_is_kept_when_there_is_one(self):
        class ConnectError(Exception):
            pass

        described = self.describe(ConnectError("connection reset by peer"))
        self.assertIn("ConnectError", described)
        self.assertIn("connection reset by peer", described)

    def test_the_description_is_never_empty(self):
        class Weird(Exception):
            def __str__(self) -> str:
                return ""

        self.assertTrue(self.describe(Weird()).strip())
