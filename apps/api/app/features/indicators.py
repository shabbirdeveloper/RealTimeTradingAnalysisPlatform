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
    at least `period + 1 + 20` candles to be a meaningful percentile (an
    honest minimum sample size, not a fixed 100 -- fewer real observations
    just means a smaller, still-real, comparison window).
    """
    series = atr_series(candles, period)
    valid = [v for v in series if v is not None]
    if len(valid) < 20:
        return None
    window = valid[-lookback:]
    current = window[-1]
    rank = sum(1 for v in window if v <= current)
    return rank / len(window) * 100


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
