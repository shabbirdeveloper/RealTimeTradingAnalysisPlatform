"""
Bounded retry with exponential backoff for provider calls (audit FIN-07).

Before this, a transient failure lost that asset's entire cycle: the error
was logged and nothing was retried until the next tick, ten minutes later.
On the crypto pairs that is a ten-minute hole in a 24/7 series; on all of
them it eventually trips the staleness gate and stands the engine down.

THE CONSTRAINT THAT SHAPES EVERYTHING HERE IS THE CREDIT BUDGET
---------------------------------------------------------------
Twelve Data's free tier allows 8 credits/minute and 800/day. Five assets
polled every 600s already costs ~720/day -- 90% of the daily ceiling
before a single retry. A conventional "3 retries per call" policy would
allow up to 2,160/day and exhaust the budget by mid-morning, at which
point EVERY asset starts failing.

So a retry policy that ignores the budget doesn't reduce downtime, it
manufactures it. Hence:

  * one retry by default, not three;
  * retries only for transient failures -- a bad key or an unknown symbol
    fails identically every time and each attempt still costs a credit;
  * a hard ceiling on total wait, so a provider's Retry-After can never
    stall the scheduler past its own tick;
  * full jitter on the backoff, so five assets failing together (which is
    what a provider outage looks like) don't retry in lockstep and arrive
    as a synchronized burst -- the one shape most likely to earn a 429.

Pure control flow with an injectable clock and sleeper, so the behaviour
is testable without waiting in real time or touching the network.
"""
from __future__ import annotations

import asyncio
import logging
import random
from dataclasses import dataclass, field
from typing import Awaitable, Callable, TypeVar

from app.market_data.errors import (
    MarketDataError,
    RateLimitError,
    TransientMarketDataError,
)

logger = logging.getLogger(__name__)

T = TypeVar("T")


@dataclass(frozen=True)
class RetryPolicy:
    # Total attempts, not retries: 2 means "try, and if it was transient,
    # try once more". See the module docstring on why this is not 4.
    max_attempts: int = 2
    base_delay_seconds: float = 1.0
    max_delay_seconds: float = 20.0
    # Nothing may make a single asset's fetch take longer than this,
    # Retry-After included. The scheduler runs assets sequentially, so one
    # asset that waits too long delays every asset after it and can push the
    # cycle past its own interval.
    max_total_wait_seconds: float = 30.0

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")


@dataclass
class RetryOutcome:
    """What it took to get the answer. Reported into system_health so the
    feed's real reliability is observable rather than inferred from the
    absence of complaints."""

    attempts: int = 1
    retries: int = 0
    rate_limited: bool = False
    waited_seconds: float = 0.0
    last_error: str | None = None
    errors: list[str] = field(default_factory=list)


def _backoff_delay(attempt: int, policy: RetryPolicy, rng: random.Random) -> float:
    """Full jitter: uniform(0, capped_exponential).

    Not the exponential value itself. Five assets failing at the same
    instant and retrying at exactly base*2^n would arrive together -- a
    thundering herd against the very provider that just failed. Jitter
    spreads them, and full jitter (rather than a narrow band around the
    target) spreads them best.
    """
    ceiling = min(policy.max_delay_seconds, policy.base_delay_seconds * (2 ** (attempt - 1)))
    return rng.uniform(0.0, ceiling)


async def call_with_retry(
    operation: Callable[[], Awaitable[T]],
    *,
    policy: RetryPolicy | None = None,
    label: str = "provider call",
    sleeper: Callable[[float], Awaitable[None]] = asyncio.sleep,
    rng: random.Random | None = None,
) -> tuple[T, RetryOutcome]:
    """Runs `operation`, retrying only transient failures.

    Raises the last error if every attempt fails -- deliberately, rather
    than returning a partial or cached result. A caller that cannot get
    real data must skip the cycle, not substitute something plausible
    (base.py's MarketDataError contract, spec section 50).
    """
    policy = policy or RetryPolicy()
    rng = rng or random.Random()
    outcome = RetryOutcome()

    for attempt in range(1, policy.max_attempts + 1):
        outcome.attempts = attempt
        try:
            result = await operation()
            return result, outcome
        except TransientMarketDataError as exc:
            outcome.last_error = str(exc)
            outcome.errors.append(str(exc))
            if isinstance(exc, RateLimitError):
                outcome.rate_limited = True

            if attempt >= policy.max_attempts:
                logger.warning("%s failed after %d attempt(s): %s", label, attempt, exc)
                raise

            delay = _backoff_delay(attempt, policy, rng)
            if isinstance(exc, RateLimitError) and exc.retry_after is not None:
                # The provider knows its own window better than our backoff
                # curve does, so prefer its number -- but only as a floor to
                # raise our wait, never to shorten it below the jittered
                # delay, and never past the total budget.
                delay = max(delay, exc.retry_after)

            remaining = policy.max_total_wait_seconds - outcome.waited_seconds
            if delay > remaining:
                # Waiting the full amount would overrun this asset's share of
                # the cycle. Giving up now and letting the next tick try is
                # strictly better than delaying every asset queued behind it.
                logger.warning(
                    "%s: giving up rather than waiting %.1fs (%.1fs budget left): %s",
                    label, delay, max(0.0, remaining), exc,
                )
                raise

            outcome.retries += 1
            outcome.waited_seconds += delay
            logger.info("%s: retrying in %.1fs after transient failure: %s", label, delay, exc)
            await sleeper(delay)
        except MarketDataError as exc:
            # Permanent: a bad key, an unknown symbol, a malformed response.
            # Retrying spends credits to receive the identical error.
            outcome.last_error = str(exc)
            outcome.errors.append(str(exc))
            raise

    # Unreachable: the loop either returns or raises.
    raise AssertionError("call_with_retry exited its loop without a result")
