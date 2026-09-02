"""
Candle anatomy, named patterns, and recent-sequence behaviour
(spec sections 14 and 15).

WHY RATIOS AND NOT PRICES
-------------------------
Everything here is expressed as a fraction of the candle's own range, so
the numbers mean the same thing on XAUUSD at 4,300 and EURUSD at 1.16. A
pattern detector written in absolute terms works on exactly one
instrument at exactly one volatility, and silently stops working when
either changes.

WHY PATTERNS ARE CONTEXT-FREE HERE
----------------------------------
A hammer is a hammer whether or not it is at support. This module reports
what the candles ARE; whether that matters is the strategy's question,
answered with the regime and the zone engine beside it. Folding context in
here would make every pattern untestable in isolation and would hide the
place where the judgement actually happens.

A NOTE ON WHAT THESE ARE WORTH
------------------------------
Candlestick patterns are among the most widely watched and most weakly
evidenced signals in trading. They are implemented because the spec asks
for them and because they belong in the feature set that
analyze_features.py can test -- not because they are assumed to work.
Nothing here should be given weight until the data says so.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# A body this small relative to range is indecision, not direction.
DOJI_BODY_RATIO = 0.1
# A wick this large relative to range is rejection.
DOMINANT_WICK_RATIO = 0.55
# A body this large relative to range is conviction.
STRONG_BODY_RATIO = 0.6


@dataclass(frozen=True)
class CandleShape:
    body_ratio: float        # |close - open| / range
    upper_wick_ratio: float
    lower_wick_ratio: float
    close_location: float    # 0.0 at the low, 1.0 at the high
    bullish: bool
    range_size: float

    @property
    def is_doji(self) -> bool:
        return self.body_ratio <= DOJI_BODY_RATIO

    @property
    def is_strong_body(self) -> bool:
        return self.body_ratio >= STRONG_BODY_RATIO


def shape_of(candle: dict) -> CandleShape:
    """Anatomy of one candle, normalised by its own range.

    A zero-range candle (every price identical) is real -- an illiquid
    minute prints them -- so it returns defined, neutral ratios rather
    than dividing by zero.
    """
    o, h, l, c = (float(candle["open"]), float(candle["high"]),
                  float(candle["low"]), float(candle["close"]))
    rng = h - l
    if rng <= 0:
        return CandleShape(0.0, 0.0, 0.0, 0.5, c >= o, 0.0)
    return CandleShape(
        body_ratio=abs(c - o) / rng,
        upper_wick_ratio=(h - max(o, c)) / rng,
        lower_wick_ratio=(min(o, c) - l) / rng,
        close_location=(c - l) / rng,
        bullish=c >= o,
        range_size=rng,
    )


def patterns(candles: list[dict]) -> list[str]:
    """Named patterns present at the END of the series, newest candle last.

    Returns every pattern that matches rather than one "winning" label:
    a bullish engulfing that is also a strong body is both, and forcing a
    single answer discards half of what was observed.
    """
    if len(candles) < 2:
        return []

    prev, cur = shape_of(candles[-2]), shape_of(candles[-1])
    po, pc = float(candles[-2]["open"]), float(candles[-2]["close"])
    co, cc = float(candles[-1]["open"]), float(candles[-1]["close"])
    ph, pl = float(candles[-2]["high"]), float(candles[-2]["low"])
    ch, cl = float(candles[-1]["high"]), float(candles[-1]["low"])

    found: list[str] = []

    if cur.is_doji:
        found.append("DOJI")
    if cur.is_strong_body:
        found.append("STRONG_BULL_BODY" if cur.bullish else "STRONG_BEAR_BODY")

    # Engulfing compares BODIES, not ranges. Comparing high-to-low instead
    # is the common mistake and turns every outside bar into an engulfing.
    if cur.bullish and not prev.bullish and cc >= po and co <= pc:
        found.append("BULLISH_ENGULFING")
    if not cur.bullish and prev.bullish and cc <= po and co >= pc:
        found.append("BEARISH_ENGULFING")

    if cur.lower_wick_ratio >= DOMINANT_WICK_RATIO and cur.body_ratio < 0.4:
        found.append("HAMMER")
    if cur.upper_wick_ratio >= DOMINANT_WICK_RATIO and cur.body_ratio < 0.4:
        found.append("SHOOTING_STAR")

    if ch <= ph and cl >= pl:
        found.append("INSIDE_BAR")
    if ch > ph and cl < pl:
        found.append("OUTSIDE_BAR")

    return found


@dataclass(frozen=True)
class SequenceReading:
    """How the last N candles behaved, not just the last one."""
    window: int
    bullish_count: int
    bearish_count: int
    average_body_ratio: float
    average_range: float
    directional_persistence: float   # -1.0 all down .. +1.0 all up
    wick_pressure: float             # -1.0 sellers .. +1.0 buyers
    patterns: list[str] = field(default_factory=list)

    @property
    def indecisive(self) -> bool:
        """Near-even direction with small bodies: the market is not going
        anywhere, whatever the last candle looked like."""
        return abs(self.directional_persistence) < 0.25 and self.average_body_ratio < 0.35


def sequence(candles: list[dict], window: int = 5) -> SequenceReading | None:
    """Behaviour over the last `window` candles (spec section 15).

    One candle is an anecdote. Three consecutive strong bodies closing near
    their highs is a different market from one such candle after four
    dojis, and only a sequence can express that.
    """
    if window <= 0:
        raise ValueError("window must be positive")
    if len(candles) < window:
        return None

    recent = candles[-window:]
    shapes = [shape_of(c) for c in recent]
    bull = sum(1 for s in shapes if s.bullish)
    bear = window - bull

    return SequenceReading(
        window=window,
        bullish_count=bull,
        bearish_count=bear,
        average_body_ratio=sum(s.body_ratio for s in shapes) / window,
        average_range=sum(s.range_size for s in shapes) / window,
        directional_persistence=(bull - bear) / window,
        # Where closes sat inside their ranges, recentred to -1..+1. Closing
        # high repeatedly means buyers kept control of each bar, which is
        # not the same as the bars being green.
        wick_pressure=(sum(s.close_location for s in shapes) / window - 0.5) * 2,
        patterns=patterns(recent),
    )
