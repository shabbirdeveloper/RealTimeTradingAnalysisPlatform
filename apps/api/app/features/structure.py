"""
Real market structure detection from real candles (spec section 6:
swing high/low, higher-high/higher-low, lower-high/lower-low, break of
structure, change of character, support/resistance, breakout/retest/
rejection) plus session features (spec section 6: Asian/London/NY
sessions and their highs/lows, previous-day high/low).

Deliberately simple, rule-based, and fully deterministic -- this is not
a claim of sophisticated pattern recognition, just an honest, real
computation from real OHLC data. Returns `None`/empty results rather
than guessing when there isn't enough history yet.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass(frozen=True)
class SwingPoint:
    index: int
    kind: str  # "high" | "low"
    price: float
    time: datetime


def find_swings(candles: list[dict], window: int = 2) -> list[SwingPoint]:
    """A simple fractal swing detector: candle i is a swing high if its
    high is the strict max among the `window` candles on each side (swing
    low, symmetric on lows). Needs at least `2 * window + 1` candles to
    find anything at all.
    """
    n = len(candles)
    swings: list[SwingPoint] = []
    if n < 2 * window + 1:
        return swings
    for i in range(window, n - window):
        highs = [float(candles[j]["high"]) for j in range(i - window, i + window + 1)]
        lows = [float(candles[j]["low"]) for j in range(i - window, i + window + 1)]
        this_high = float(candles[i]["high"])
        this_low = float(candles[i]["low"])
        if this_high == max(highs) and highs.count(this_high) == 1:
            swings.append(SwingPoint(index=i, kind="high", price=this_high, time=candles[i]["open_time"]))
        if this_low == min(lows) and lows.count(this_low) == 1:
            swings.append(SwingPoint(index=i, kind="low", price=this_low, time=candles[i]["open_time"]))
    return swings


@dataclass(frozen=True)
class StructureReading:
    sequence: str | None  # "HH_HL" | "LH_LL" | "MIXED" | None (insufficient data)
    bos: bool  # break of structure: latest close beyond the most recent opposing swing
    choch: bool  # change of character: sequence just flipped direction
    support: float | None
    resistance: float | None
    notes: list[str] = field(default_factory=list)


def classify_structure(candles: list[dict], window: int = 2) -> StructureReading:
    swings = find_swings(candles, window=window)
    highs = [s for s in swings if s.kind == "high"]
    lows = [s for s in swings if s.kind == "low"]

    if len(highs) < 2 or len(lows) < 2:
        return StructureReading(sequence=None, bos=False, choch=False, support=None, resistance=None,
                                 notes=["Not enough swing points yet for a structure read."])

    higher_high = highs[-1].price > highs[-2].price
    higher_low = lows[-1].price > lows[-2].price
    lower_high = highs[-1].price < highs[-2].price
    lower_low = lows[-1].price < lows[-2].price

    if higher_high and higher_low:
        sequence = "HH_HL"
    elif lower_high and lower_low:
        sequence = "LH_LL"
    else:
        sequence = "MIXED"

    resistance = highs[-1].price
    support = lows[-1].price
    last_close = float(candles[-1]["close"])

    bos = last_close > resistance or last_close < support
    notes: list[str] = []
    if sequence == "HH_HL":
        notes.append("Higher-high / higher-low sequence intact.")
    elif sequence == "LH_LL":
        notes.append("Lower-high / lower-low sequence intact.")
    else:
        notes.append("Mixed swing sequence — no clean directional structure.")
    if last_close > resistance:
        notes.append("Break of structure — price closed above the last swing high.")
    elif last_close < support:
        notes.append("Break of structure — price closed below the last swing low.")
    else:
        notes.append(f"Trading inside the last swing range ({support:.5g} - {resistance:.5g}).")

    # Change of character: this is the first swing-high/low pair to break
    # the *prior* two-swing trend, i.e. the sequence just flipped.
    choch = False
    if len(highs) >= 3 and len(lows) >= 3:
        prior_seq_up = highs[-2].price > highs[-3].price and lows[-2].price > lows[-3].price
        prior_seq_down = highs[-2].price < highs[-3].price and lows[-2].price < lows[-3].price
        if prior_seq_up and sequence == "LH_LL":
            choch = True
            notes.append("Change of character — prior uptrend structure just broke down.")
        elif prior_seq_down and sequence == "HH_HL":
            choch = True
            notes.append("Change of character — prior downtrend structure just broke up.")

    return StructureReading(sequence=sequence, bos=bos, choch=choch, support=support, resistance=resistance, notes=notes)


def session_for_time(now: datetime) -> str:
    """Mirrors apps/web's sessionForTime() exactly -- pure UTC-hour lookup,
    genuinely accurate regardless of demo/real data.
    """
    h = now.astimezone(timezone.utc).hour
    london = 7 <= h < 16
    ny = 12 <= h < 21
    if london and ny:
        return "LONDON_NY_OVERLAP"
    if london:
        return "LONDON"
    if ny:
        return "NEW_YORK"
    return "ASIAN"


@dataclass(frozen=True)
class SessionRanges:
    asian_high: float | None
    asian_low: float | None
    london_high: float | None
    london_low: float | None
    prev_day_high: float | None
    prev_day_low: float | None


def session_ranges(m5_candles: list[dict], now: datetime) -> SessionRanges:
    """Computed from real M5 candles grouped by UTC calendar day / session
    window. Returns None for any range that doesn't have candles covering
    it yet (e.g. collector only just started, or it's still the Asian
    session so London hasn't opened today).
    """
    now_utc = now.astimezone(timezone.utc)
    today = now_utc.date()

    def in_range(c: dict, day, h_start: int, h_end: int) -> bool:
        t = c["open_time"].astimezone(timezone.utc)
        return t.date() == day and h_start <= t.hour < h_end

    asian_candles = [c for c in m5_candles if in_range(c, today, 0, 7)]
    london_candles = [c for c in m5_candles if in_range(c, today, 7, 12)]
    prev_day = today.fromordinal(today.toordinal() - 1)
    prev_day_candles = [c for c in m5_candles if c["open_time"].astimezone(timezone.utc).date() == prev_day]

    def hi_lo(cs: list[dict]) -> tuple[float | None, float | None]:
        if not cs:
            return None, None
        return max(float(c["high"]) for c in cs), min(float(c["low"]) for c in cs)

    asian_high, asian_low = hi_lo(asian_candles)
    london_high, london_low = hi_lo(london_candles)
    prev_day_high, prev_day_low = hi_lo(prev_day_candles)

    return SessionRanges(
        asian_high=asian_high, asian_low=asian_low,
        london_high=london_high, london_low=london_low,
        prev_day_high=prev_day_high, prev_day_low=prev_day_low,
    )
