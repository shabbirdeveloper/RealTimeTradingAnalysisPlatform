"""
Liquidity sweep detection (brief section 7).

WHAT A SWEEP IS
---------------
Price pushes THROUGH a level where resting orders sit -- a confirmed swing
low, say -- takes them, and then closes back on the original side. The
break was not a breakout; it was the market reaching down for liquidity
and rejecting the level.

    bullish sweep:  low  <  confirmed swing low   AND  close > that low
    bearish sweep:  high >  confirmed swing high  AND  close < that high

plus evidence of rejection in the candle's own shape.

WHY THE CONFIRMATION RULE IS THE WHOLE THING
--------------------------------------------
`find_swings` is a fractal detector: a candle is a swing low only if its
low is the strict minimum among the `window` candles on EACH side. That
means a swing at index i is not knowable until index i + window has
closed.

So a sweep candle must never be allowed to confirm the very swing it is
sweeping. Doing so is look-ahead of the most seductive kind: it produces
beautiful historical sweeps that could not have been seen at the time, and
a backtest built on them reports an edge that evaporates live. Every swing
used here is required to be confirmed strictly BEFORE the sweep candle --
`swing.index + window < sweep_index` -- and there is a test that fails if
that inequality is ever relaxed.

WHY WICKS ARE MEASURED IN ATR AND IN RATIOS
-------------------------------------------
Both, because they answer different questions. The RATIO (wick / range)
says the candle rejected the level; the ATR-scaled penetration says the
sweep was big enough to have actually taken orders rather than being a
one-tick graze that happens constantly in a quiet market. A rule using
only the ratio fires on noise; one using only ATR fires on any large
candle regardless of shape.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.features.indicators import atr_latest
from app.features.structure import SwingPoint, find_swings


@dataclass(frozen=True)
class SweepConfig:
    """Every threshold, in one place (brief section 23). These are starting
    values, not findings; calibration replaces them."""

    swing_window: int = 2
    # How far back to look for a level worth sweeping. Beyond this the
    # level is old enough that the orders behind it have likely gone.
    lookback: int = 40
    # The wick beyond the level must be at least this fraction of the
    # candle's own range -- the rejection evidence.
    min_wick_ratio: float = 0.33
    # ...and the penetration must be at least this many ATRs, so a one-tick
    # graze in a quiet market does not count as having taken liquidity.
    min_penetration_atr: float = 0.10
    # ...but not more than this: a candle that closes far beyond the level
    # is a breakout, not a sweep, and calling it a sweep inverts the trade.
    max_penetration_atr: float = 2.50
    # The close must sit in this part of the candle's range, on the side
    # that rejected. 0.55 means "above the midpoint" for a bullish sweep.
    min_close_location: float = 0.55
    # A body larger than this fraction of range is a directional candle
    # whose wick is incidental, not a rejection.
    max_body_ratio: float = 0.70


DEFAULT_SWEEP_CONFIG = SweepConfig()


@dataclass(frozen=True)
class CandleAnatomy:
    """The four measurements every rule here is built from."""

    body: float
    upper_wick: float
    lower_wick: float
    range_: float
    close_location: float  # 0.0 at the low, 1.0 at the high
    bullish: bool

    @property
    def body_ratio(self) -> float:
        return self.body / self.range_ if self.range_ else 0.0

    @property
    def upper_wick_ratio(self) -> float:
        return self.upper_wick / self.range_ if self.range_ else 0.0

    @property
    def lower_wick_ratio(self) -> float:
        return self.lower_wick / self.range_ if self.range_ else 0.0


def anatomy(candle: dict) -> CandleAnatomy:
    o = float(candle["open"])
    h = float(candle["high"])
    l = float(candle["low"])
    c = float(candle["close"])
    range_ = h - l
    return CandleAnatomy(
        body=abs(c - o),
        upper_wick=h - max(o, c),
        lower_wick=min(o, c) - l,
        range_=range_,
        # A doji whose high equals its low has no location. 0.5 is the only
        # non-arbitrary answer, and the caller's thresholds reject it anyway.
        close_location=((c - l) / range_) if range_ else 0.5,
        bullish=c >= o,
    )


@dataclass(frozen=True)
class Sweep:
    direction: str            # "BULLISH" | "BEARISH"
    level: float              # the swing price that was swept
    level_index: int
    penetration_atr: float    # how far beyond the level, in ATRs
    wick_ratio: float         # the rejecting wick as a fraction of range
    close_location: float
    touches: int              # how many prior swings sat at this level
    reason: str

    @property
    def strength(self) -> int:
        """0-100. Deliberately a blend of three independent measurements,
        so no single one can carry a weak sweep: how decisively the candle
        rejected (wick), where it closed, and how many times the level had
        been respected before."""
        wick = min(1.0, self.wick_ratio / 0.6) * 45
        close = min(1.0, abs(self.close_location - 0.5) / 0.4) * 35
        history = min(1.0, (self.touches - 1) / 2.0) * 20
        return int(round(wick + close + history))


def detect_sweep(
    candles: list[dict],
    *,
    config: SweepConfig = DEFAULT_SWEEP_CONFIG,
) -> Sweep | None:
    """Whether the LAST candle in `candles` swept liquidity.

    `candles` must contain closed bars only, oldest first. The last one is
    the candidate; every level it is tested against comes from strictly
    earlier, confirmed structure.
    """
    if len(candles) < config.swing_window * 2 + 3:
        return None

    atr = atr_latest(candles)
    if not atr:
        return None

    sweep_index = len(candles) - 1
    candle = anatomy(candles[sweep_index])
    if candle.range_ <= 0:
        return None

    # A candle that is mostly body is going somewhere; its wick is a side
    # effect. Sweeps are wick-dominant by construction.
    if candle.body_ratio > config.max_body_ratio:
        return None

    swings = find_swings(candles, window=config.swing_window)

    # THE look-ahead guard. A swing at index i is only knowable once
    # i + window bars have closed, so a swing the sweep candle itself
    # helped confirm did not exist at decision time.
    confirmed = [
        s for s in swings
        if s.index + config.swing_window < sweep_index
        and sweep_index - s.index <= config.lookback
    ]
    if not confirmed:
        return None

    low = float(candles[sweep_index]["low"])
    high = float(candles[sweep_index]["high"])
    close = float(candles[sweep_index]["close"])

    bullish = _bullish_sweep(confirmed, low, close, atr, candle, config)
    bearish = _bearish_sweep(confirmed, high, close, atr, candle, config)

    if bullish and bearish:
        # An outside candle that pierced both sides and closed in the
        # middle has taken liquidity in both directions and committed to
        # neither. Returning the "stronger" one would manufacture a
        # direction out of a genuinely two-sided candle.
        return None
    return bullish or bearish


def _bullish_sweep(
    swings: list[SwingPoint], low: float, close: float, atr: float,
    candle: CandleAnatomy, config: SweepConfig,
) -> Sweep | None:
    lows = [s for s in swings if s.kind == "low" and low < s.price <= close]
    if not lows:
        return None
    # The DEEPEST level actually swept and reclaimed -- the one that took
    # the most orders. The nearest would understate the move.
    level = min(lows, key=lambda s: s.price)

    penetration = (level.price - low) / atr
    if not (config.min_penetration_atr <= penetration <= config.max_penetration_atr):
        return None
    if candle.lower_wick_ratio < config.min_wick_ratio:
        return None
    if candle.close_location < config.min_close_location:
        return None

    touches = _touches(swings, level.price, atr, "low")
    return Sweep(
        direction="BULLISH", level=level.price, level_index=level.index,
        penetration_atr=penetration, wick_ratio=candle.lower_wick_ratio,
        close_location=candle.close_location, touches=touches,
        reason=(
            f"swept the swing low at {level.price:.5f} by {penetration:.2f} ATR "
            f"and closed back above it ({candle.lower_wick_ratio:.0%} lower wick)"
        ),
    )


def _bearish_sweep(
    swings: list[SwingPoint], high: float, close: float, atr: float,
    candle: CandleAnatomy, config: SweepConfig,
) -> Sweep | None:
    highs = [s for s in swings if s.kind == "high" and close <= s.price < high]
    if not highs:
        return None
    level = max(highs, key=lambda s: s.price)

    penetration = (high - level.price) / atr
    if not (config.min_penetration_atr <= penetration <= config.max_penetration_atr):
        return None
    if candle.upper_wick_ratio < config.min_wick_ratio:
        return None
    if candle.close_location > (1.0 - config.min_close_location):
        return None

    touches = _touches(swings, level.price, atr, "high")
    return Sweep(
        direction="BEARISH", level=level.price, level_index=level.index,
        penetration_atr=penetration, wick_ratio=candle.upper_wick_ratio,
        close_location=candle.close_location, touches=touches,
        reason=(
            f"swept the swing high at {level.price:.5f} by {penetration:.2f} ATR "
            f"and closed back below it ({candle.upper_wick_ratio:.0%} upper wick)"
        ),
    )


def _touches(swings: list[SwingPoint], price: float, atr: float, kind: str) -> int:
    """How many confirmed swings of the same kind sat at this level.

    A level touched three times held three times, and sweeping it means
    something the first touch did not. Tolerance is a quarter-ATR so the
    count reflects the same level rather than exact float equality.
    """
    tolerance = atr * 0.25
    return sum(1 for s in swings if s.kind == kind and abs(s.price - price) <= tolerance)
