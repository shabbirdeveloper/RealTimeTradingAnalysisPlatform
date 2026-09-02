"""
Real technical indicators computed from real stored candles.

Every function here is pure (no I/O, no randomness) and returns ``None``
when there isn't yet enough candle history to compute the value honestly,
rather than a partially-converged or fabricated number. Per the project's
"no fake data, ever" rule (spec section 50), a missing indicator must show
up as `None` and flow through to an explicit "insufficient data" state --
it must never be silently zero-filled or estimated from too little data.

`candles` throughout is a list of dicts (or objects with the same keys)
with at least: open, high, low, close, and is expected OLDEST-FIRST
(index 0 = earliest), matching the convention used by
`app.storage.candle_repository.fetch_recent_candles` once reversed.
"""
from __future__ import annotations

from dataclasses import dataclass


def _closes(candles: list[dict]) -> list[float]:
    return [float(c["close"]) for c in candles]


def ema_series(values: list[float], period: int) -> list[float | None]:
    """Standard EMA: seeded with the SMA of the first `period` values, then
    smoothed forward. Returns one entry per input value; the first
    `period - 1` entries are None (not enough history yet to seed).
    """
    if period <= 0:
        raise ValueError("period must be positive")
    n = len(values)
    out: list[float | None] = [None] * n
    if n < period:
        return out
    k = 2 / (period + 1)
    seed = sum(values[:period]) / period
    out[period - 1] = seed
    prev = seed
    for i in range(period, n):
        prev = values[i] * k + prev * (1 - k)
        out[i] = prev
    return out


def ema_latest(values: list[float], period: int) -> float | None:
    series = ema_series(values, period)
    return series[-1] if series else None


def ema_slope(values: list[float], period: int, lookback: int = 3) -> float | None:
    """Simple slope of the EMA over the last `lookback` closed bars, as a
    percentage of the EMA's own level (so it's comparable across assets
    with very different price scales, e.g. XAUUSD vs EURUSD).
    """
    series = ema_series(values, period)
    if len(series) <= lookback or series[-1] is None or series[-1 - lookback] is None:
        return None
    latest = series[-1]
    prior = series[-1 - lookback]
    if latest is None or prior is None or prior == 0:
        return None
    return (latest - prior) / abs(prior) * 100


def rsi_latest(values: list[float], period: int = 14) -> float | None:
    """Wilder's RSI. Needs `period + 1` closes minimum."""
    if len(values) < period + 1:
        return None
    gains = 0.0
    losses = 0.0
    for i in range(1, period + 1):
        delta = values[i] - values[i - 1]
        if delta >= 0:
            gains += delta
        else:
            losses -= delta
    avg_gain = gains / period
    avg_loss = losses / period
    for i in range(period + 1, len(values)):
        delta = values[i] - values[i - 1]
        gain = max(delta, 0.0)
        loss = max(-delta, 0.0)
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def rsi_slope(values: list[float], period: int = 14) -> str | None:
    """RISING / FALLING / FLAT based on RSI now vs 3 candles ago. None if
    there isn't enough history for both readings.
    """
    if len(values) < period + 1 + 3:
        return None
    now = rsi_latest(values, period)
    prior = rsi_latest(values[:-3], period)
    if now is None or prior is None:
        return None
    diff = now - prior
    if diff > 3:
        return "RISING"
    if diff < -3:
        return "FALLING"
    return "FLAT"


@dataclass(frozen=True)
class MacdResult:
    macd: float
    signal: float
    histogram: float
    histogram_prev: float | None


def macd_latest(values: list[float], fast: int = 12, slow: int = 26, signal: int = 9) -> MacdResult | None:
    """Standard MACD(12,26,9). Needs at least `slow + signal` closes so the
    signal line itself has converged past its own seed point.
    """
    if len(values) < slow + signal:
        return None
    fast_series = ema_series(values, fast)
    slow_series = ema_series(values, slow)
    macd_line: list[float | None] = [
        (f - s) if f is not None and s is not None else None
        for f, s in zip(fast_series, slow_series)
    ]
    # Signal line = EMA of the MACD line, computed only over the portion
    # where the MACD line itself is defined.
    first_valid = next((i for i, v in enumerate(macd_line) if v is not None), None)
    if first_valid is None or len(macd_line) - first_valid < signal:
        return None
    macd_valid = [v for v in macd_line[first_valid:] if v is not None]
    signal_series = ema_series(macd_valid, signal)
    if signal_series[-1] is None:
        return None
    macd_now = macd_valid[-1]
    signal_now = signal_series[-1]
    histogram_now = macd_now - signal_now
    histogram_prev = None
    if len(macd_valid) > 1 and len(signal_series) > 1 and signal_series[-2] is not None:
        histogram_prev = macd_valid[-2] - signal_series[-2]
    return MacdResult(macd=macd_now, signal=signal_now, histogram=histogram_now, histogram_prev=histogram_prev)


def atr_series(candles: list[dict], period: int = 14) -> list[float | None]:
    """Wilder's ATR. Needs `period + 1` candles minimum (the first true
    range needs a previous close).
    """
    n = len(candles)
    out: list[float | None] = [None] * n
    if n < period + 1:
        return out
    true_ranges: list[float] = []
    for i in range(1, n):
        high = float(candles[i]["high"])
        low = float(candles[i]["low"])
        prev_close = float(candles[i - 1]["close"])
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        true_ranges.append(tr)
    # true_ranges[0] corresponds to candle index 1
    seed = sum(true_ranges[:period]) / period
    out[period] = seed
    prev = seed
    for i in range(period, len(true_ranges)):
        prev = (prev * (period - 1) + true_ranges[i]) / period
        out[i + 1] = prev
    return out


def atr_latest(candles: list[dict], period: int = 14) -> float | None:
    series = atr_series(candles, period)
    return series[-1] if series else None


def atr_percentile(candles: list[dict], period: int = 14, lookback: int = 100) -> float | None:
    """Where the current ATR sits vs its own recent history (0-100). Needs
    at least 20 ATR observations to be a meaningful percentile (an honest
    minimum sample size, not a fixed 100 -- fewer real observations just
    means a smaller, still-real, comparison window).

    Ties use the midpoint convention: a value equal to others counts as
    half-below, half-above. This matters -- counting ties as "below"
    would score a perfectly flat-volatility market at the 100th
    percentile and have the regime engine call it HIGH_VOLATILITY, which
    is exactly backwards. Steady volatility should read as ordinary (50),
    and it does.
    """
    series = atr_series(candles, period)
    valid = [v for v in series if v is not None]
    if len(valid) < 20:
        return None
    window = valid[-lookback:]
    current = window[-1]
    below = sum(1 for v in window if v < current)
    equal = sum(1 for v in window if v == current)
    return (below + 0.5 * equal) / len(window) * 100


@dataclass(frozen=True)
class BollingerResult:
    mid: float
    upper: float
    lower: float
    width_pct: float  # (upper - lower) / mid * 100


def bollinger_latest(values: list[float], period: int = 20, num_std: float = 2.0) -> BollingerResult | None:
    if len(values) < period:
        return None
    window = values[-period:]
    mid = sum(window) / period
    variance = sum((v - mid) ** 2 for v in window) / period
    std = variance ** 0.5
    upper = mid + num_std * std
    lower = mid - num_std * std
    width_pct = ((upper - lower) / mid * 100) if mid else 0.0
    return BollingerResult(mid=mid, upper=upper, lower=lower, width_pct=width_pct)


# ---------------------------------------------------------------------------
# Trend strength, oscillator normalisation, rate of change (spec sections 8/10)
# ---------------------------------------------------------------------------


def _wilder_smooth(values: list[float], period: int) -> list[float | None]:
    """Wilder's smoothing, as ADX is actually defined.

    Not an EMA with a fiddled multiplier: Wilder seeds with a plain SUM of
    the first `period` values and then carries `prev - prev/period + new`.
    Substituting a standard EMA is the common shortcut and it produces
    visibly different ADX values, which then disagree with every chart the
    user compares against.
    """
    n = len(values)
    out: list[float | None] = [None] * n
    if n < period:
        return out
    total = sum(values[:period])
    out[period - 1] = total
    for i in range(period, n):
        total = total - (total / period) + values[i]
        out[i] = total
    return out


@dataclass(frozen=True)
class AdxResult:
    adx: float
    plus_di: float
    minus_di: float

    @property
    def trending(self) -> bool:
        """The conventional reading. 25 is a convention, not a law -- it is
        named here so the number appears once rather than scattered."""
        return self.adx >= 25.0


ADX_TRENDING_THRESHOLD = 25.0


def adx_latest(candles: list[dict], period: int = 14) -> AdxResult | None:
    """Average Directional Index with its two directional components.

    ADX measures how strongly price is trending WITHOUT saying which way --
    +DI and -DI carry the direction. That separation is the whole reason to
    have it: the regime engine needs "is this a trend at all", which is a
    different question from "up or down", and conflating them is how a
    strong downtrend gets classified as a weak uptrend.

    Needs 2 * period + 1 candles: `period` to seed Wilder's smoothing of DM
    and TR, then another `period` to average DX into ADX.
    """
    if period <= 0:
        raise ValueError("period must be positive")
    if len(candles) < 2 * period + 1:
        return None

    plus_dm: list[float] = []
    minus_dm: list[float] = []
    tr: list[float] = []

    for prev, cur in zip(candles, candles[1:]):
        high, low = float(cur["high"]), float(cur["low"])
        prev_high, prev_low, prev_close = (
            float(prev["high"]), float(prev["low"]), float(prev["close"]),
        )
        up_move = high - prev_high
        down_move = prev_low - low
        # Only the LARGER move counts, and only if positive. Awarding both
        # on an outside bar double-counts a single candle's expansion.
        plus_dm.append(up_move if (up_move > down_move and up_move > 0) else 0.0)
        minus_dm.append(down_move if (down_move > up_move and down_move > 0) else 0.0)
        tr.append(max(high - low, abs(high - prev_close), abs(low - prev_close)))

    sm_plus = _wilder_smooth(plus_dm, period)
    sm_minus = _wilder_smooth(minus_dm, period)
    sm_tr = _wilder_smooth(tr, period)

    dx: list[float] = []
    for p, m, t in zip(sm_plus, sm_minus, sm_tr):
        if p is None or m is None or t is None or t == 0:
            continue
        plus_di = 100 * p / t
        minus_di = 100 * m / t
        denom = plus_di + minus_di
        dx.append(0.0 if denom == 0 else 100 * abs(plus_di - minus_di) / denom)

    if len(dx) < period:
        return None

    adx = sum(dx[:period]) / period
    for value in dx[period:]:
        adx = (adx * (period - 1) + value) / period

    last_tr = sm_tr[-1]
    if last_tr is None or last_tr == 0:
        return None
    last_plus, last_minus = sm_plus[-1], sm_minus[-1]
    if last_plus is None or last_minus is None:
        return None

    return AdxResult(
        adx=adx,
        plus_di=100 * last_plus / last_tr,
        minus_di=100 * last_minus / last_tr,
    )


def rsi_series(values: list[float], period: int = 14) -> list[float | None]:
    """RSI at every point, which Stochastic RSI needs. `rsi_latest` stays as
    the cheap path for callers that only want the last value."""
    n = len(values)
    out: list[float | None] = [None] * n
    if n <= period:
        return out

    gains = 0.0
    losses = 0.0
    for i in range(1, period + 1):
        change = values[i] - values[i - 1]
        gains += max(change, 0.0)
        losses += max(-change, 0.0)
    avg_gain = gains / period
    avg_loss = losses / period
    out[period] = 100.0 if avg_loss == 0 else 100 - 100 / (1 + avg_gain / avg_loss)

    for i in range(period + 1, n):
        change = values[i] - values[i - 1]
        avg_gain = (avg_gain * (period - 1) + max(change, 0.0)) / period
        avg_loss = (avg_loss * (period - 1) + max(-change, 0.0)) / period
        out[i] = 100.0 if avg_loss == 0 else 100 - 100 / (1 + avg_gain / avg_loss)
    return out


def stoch_rsi_latest(values: list[float], period: int = 14, lookback: int = 14) -> float | None:
    """Where RSI sits inside its own recent range, 0-100.

    RSI at 58 says almost nothing on its own. RSI at 58 when it has spent
    the last fourteen bars between 55 and 60 is a different market from RSI
    at 58 after ranging 30 to 70. Stochastic RSI is that normalisation.

    Returns None -- not 50 -- when RSI has been perfectly flat, because a
    zero-width range has no position within it, and 50 would read as
    "neutral" when the truth is "undefined".
    """
    rsis = [r for r in rsi_series(values, period) if r is not None]
    if len(rsis) < lookback:
        return None
    window = rsis[-lookback:]
    low, high = min(window), max(window)
    if high == low:
        return None
    return 100 * (window[-1] - low) / (high - low)


def rate_of_change(values: list[float], period: int = 10) -> float | None:
    """Percentage change over `period` bars."""
    if period <= 0:
        raise ValueError("period must be positive")
    if len(values) <= period:
        return None
    base = values[-period - 1]
    if base == 0:
        return None
    return 100 * (values[-1] - base) / base


def momentum_acceleration(values: list[float], period: int = 5) -> float | None:
    """Whether momentum is building or fading: the change in rate of change.

    Positive means the move is speeding up, negative that it is running out
    of energy -- which is the distinction between a trend to join and one to
    stay out of, and neither RSI nor MACD states it directly.
    """
    if len(values) <= 2 * period:
        return None
    recent = rate_of_change(values, period)
    earlier = rate_of_change(values[:-period], period)
    if recent is None or earlier is None:
        return None
    return recent - earlier
