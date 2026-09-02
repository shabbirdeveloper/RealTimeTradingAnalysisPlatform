"""
Per-timeframe bias (spec section 5/6): combines real EMA structure, RSI,
MACD, and swing structure into a BULLISH / BEARISH / NEUTRAL read with a
0-100 strength and human-readable notes -- the real equivalent of the
frontend demo engine's generateTimeframes().

Returns an explicit `insufficient_data` flag rather than guessing when
the underlying indicators aren't computable yet for this timeframe.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.features import indicators as ind
from app.features import structure as struct


@dataclass(frozen=True)
class TimeframeBias:
    timeframe: str
    bias: str  # "BULLISH" | "BEARISH" | "NEUTRAL"
    strength: int  # 0-100
    notes: list[str] = field(default_factory=list)
    insufficient_data: bool = False


def bias_for_timeframe(timeframe: str, candles: list[dict], *, min_votes: int = 2) -> TimeframeBias:
    closes = [float(c["close"]) for c in candles]

    ema20 = ind.ema_latest(closes, 20)
    ema50 = ind.ema_latest(closes, 50)
    ema200 = ind.ema_latest(closes, 200)
    rsi = ind.rsi_latest(closes, 14)
    macd = ind.macd_latest(closes)
    struct_reading = struct.classify_structure(candles)

    have_core = ema20 is not None and ema50 is not None and rsi is not None
    if not have_core:
        return TimeframeBias(
            timeframe=timeframe, bias="NEUTRAL", strength=0,
            notes=[f"Not enough {timeframe} history yet to compute EMA20/50 and RSI."],
            insufficient_data=True,
        )

    price = closes[-1]
    votes = 0
    bull_notes: list[str] = []
    bear_notes: list[str] = []

    if price > ema20 and ema20 > ema50:
        votes += 1
        bull_notes.append("Price above EMA20/50")
    elif price < ema20 and ema20 < ema50:
        votes -= 1
        bear_notes.append("Price below EMA20/50")

    # EMA200 is included as a full vote alongside the others below rather
    # than hand-tuned to a lower weight -- there is no principled way to
    # pick relative indicator weights without validating them against real
    # outcomes, and that validation is explicitly the backtesting engine's
    # job (spec section 13), not something to guess at here. Once
    # `/admin/backtesting` can run against real signal history, these
    # weights should move from "one vote each" to whatever the data shows.
    if ema200 is not None:
        if price > ema200:
            votes += 1
            bull_notes.append("Price above EMA200")
        elif price < ema200:
            votes -= 1
            bear_notes.append("Price below EMA200")

    if rsi > 55:
        votes += 1
        bull_notes.append("RSI trending up")
    elif rsi < 45:
        votes -= 1
        bear_notes.append("RSI trending down")

    if macd is not None:
        if macd.histogram > 0:
            votes += 1
            bull_notes.append("MACD histogram positive" + (" and expanding" if macd.histogram_prev is not None and macd.histogram > macd.histogram_prev else ""))
        elif macd.histogram < 0:
            votes -= 1
            bear_notes.append("MACD histogram negative" + (" and expanding" if macd.histogram_prev is not None and macd.histogram < macd.histogram_prev else ""))

    if struct_reading.sequence == "HH_HL":
        votes += 1
        bull_notes.append("Higher-high / higher-low structure")
    elif struct_reading.sequence == "LH_LL":
        votes -= 1
        bear_notes.append("Lower-high / lower-low structure")

    # `min_votes` used to be the literal 2. It governs how often a timeframe
    # reads NEUTRAL -- and since a NEUTRAL vote can never agree with
    # anything, it silently governs the multi-timeframe gate downstream. A
    # number with that much leverage should be measurable, not baked in.
    if votes >= min_votes:
        bias = "BULLISH"
        notes = bull_notes or ["Bullish confluence across indicators."]
    elif votes <= -min_votes:
        bias = "BEARISH"
        notes = bear_notes or ["Bearish confluence across indicators."]
    else:
        bias = "NEUTRAL"
        notes = ["No clear directional confluence."] if not struct_reading.notes else [struct_reading.notes[0]]

    strength = max(0, min(100, round(50 + votes * 14)))

    return TimeframeBias(timeframe=timeframe, bias=bias, strength=strength, notes=notes[:1], insufficient_data=False)
