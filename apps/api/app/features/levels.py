"""
Support and resistance as scored zones (spec section 13).

WHY ZONES AND NOT LINES
-----------------------
Price does not turn at a number, it turns in a neighbourhood. Two swing
lows a few ticks apart are one level that was tested twice, not two
levels tested once each -- and treating them as two is how a "level" ends
up with a touch count of one and no strength worth reading.

So nearby swings are clustered, and the cluster's width comes from ATR
rather than a fixed percentage. A 3-pip band is a wide zone on EURUSD and
a rounding error on XAUUSD; ATR is the only tolerance that means the same
thing on both, and it also adapts when the same instrument gets calmer or
wilder.

WHAT MAKES A ZONE STRONG
------------------------
Three things, and they are kept separate rather than folded into one
number at the source:

  touches      how many distinct swings formed it
  recency      how recently price last reacted there
  reaction     how far price actually moved away from it

A level touched five times last year and ignored since is not the same
as one touched twice this morning, and a level price merely grazed is not
the same as one it bounced 2 ATR off. `strength` combines them, but the
components stay on the object so a caller can disagree with the weighting
without recomputing anything.

WHAT THIS IS FOR
----------------
Spec section 13's rule: never signal CALL directly beneath strong
resistance, never PUT directly above strong support. `blocking_zone`
answers exactly that question and nothing else, so the rule lives in one
place instead of being re-derived at each call site.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.features import indicators as ind
from app.features import structure as struct

# How far apart two swings can sit and still be the same zone, in ATR.
# 0.5 is deliberately tight: merging too eagerly produces one enormous
# "zone" spanning the range, which blocks every signal and looks like the
# filter working.
CLUSTER_ATR_FRACTION = 0.5

# A zone further than this from price cannot affect the next few bars, so
# it is not worth carrying into a decision.
RELEVANT_ATR_DISTANCE = 4.0

# Below this, a zone is not evidence of anything -- one touch is a swing,
# not a level.
MIN_TOUCHES = 2


@dataclass(frozen=True)
class Zone:
    price: float
    kind: str  # "SUPPORT" | "RESISTANCE"
    touches: int
    strength: int  # 0-100
    last_touch_index: int
    best_reaction_atr: float
    distance_atr: float

    @property
    def is_strong(self) -> bool:
        return self.strength >= 60


def _cluster(prices: list[tuple[int, float]], tolerance: float) -> list[list[tuple[int, float]]]:
    """Group swings whose prices sit within `tolerance` of the group's mean.

    Compared against the running MEAN rather than the first member, so a
    long drift of nearly-touching swings cannot chain into one zone far
    wider than the tolerance -- the classic single-linkage failure.
    """
    if not prices:
        return []
    ordered = sorted(prices, key=lambda p: p[1])
    groups: list[list[tuple[int, float]]] = [[ordered[0]]]
    for item in ordered[1:]:
        current = groups[-1]
        mean = sum(p for _, p in current) / len(current)
        if abs(item[1] - mean) <= tolerance:
            current.append(item)
        else:
            groups.append([item])
    return groups


def find_zones(candles: list[dict], *, window: int = 2, atr_period: int = 14) -> list[Zone]:
    """Scored support and resistance zones, nearest to price first.

    Returns [] rather than guessing when there is not enough history for
    ATR -- a zone width derived from nothing is not a zone.
    """
    if len(candles) < atr_period + 2:
        return []
    atr = ind.atr_latest(candles, atr_period)
    if not atr or atr <= 0:
        return []

    swings = struct.find_swings(candles, window=window)
    if not swings:
        return []

    price = float(candles[-1]["close"])
    tolerance = atr * CLUSTER_ATR_FRACTION
    last_index = len(candles) - 1
    zones: list[Zone] = []

    for kind, swing_kind in (("RESISTANCE", "high"), ("SUPPORT", "low")):
        points = [(s.index, s.price) for s in swings if s.kind == swing_kind]
        for group in _cluster(points, tolerance):
            if len(group) < MIN_TOUCHES:
                continue
            level = sum(p for _, p in group) / len(group)
            distance_atr = abs(price - level) / atr
            if distance_atr > RELEVANT_ATR_DISTANCE:
                continue

            newest = max(i for i, _ in group)
            reaction = _best_reaction(candles, group, kind, atr)

            # Touches saturate: a level tested twice is meaningfully
            # different from once, five times from twice, and twelve from
            # five hardly at all. Linear scoring would let an old, heavily
            # grazed level outrank a fresh, decisive one.
            touch_score = min(40.0, 14.0 * (len(group) ** 0.7))
            recency_score = 30.0 * max(0.0, 1.0 - (last_index - newest) / max(1, len(candles)))
            reaction_score = min(30.0, 15.0 * reaction)

            zones.append(Zone(
                price=level,
                kind=kind,
                touches=len(group),
                strength=int(round(min(100.0, touch_score + recency_score + reaction_score))),
                last_touch_index=newest,
                best_reaction_atr=reaction,
                distance_atr=distance_atr,
            ))

    zones.sort(key=lambda z: z.distance_atr)
    return zones


def _best_reaction(
    candles: list[dict], group: list[tuple[int, float]], kind: str, atr: float
) -> float:
    """The largest move away from this zone after any of its touches, in ATR.

    Measured over the ten bars following each touch. A level price merely
    grazed and a level it bounced two ATR off both have a touch count; only
    this tells them apart.
    """
    best = 0.0
    for index, level in group:
        window = candles[index + 1: index + 11]
        if not window:
            continue
        if kind == "SUPPORT":
            move = max(float(c["high"]) for c in window) - level
        else:
            move = level - min(float(c["low"]) for c in window)
        best = max(best, move / atr)
    return best


def blocking_zone(zones: list[Zone], direction: str, *, within_atr: float = 1.0) -> Zone | None:
    """The strong zone standing in the way of `direction`, if any.

    Spec section 13: never CALL directly beneath strong resistance, never
    PUT directly above strong support. Only zones on the side price would
    have to travel through count -- support beneath a CALL is help, not an
    obstacle, and an implementation that ignores the sign turns every level
    into a blocker.
    """
    if direction not in ("CALL", "PUT"):
        return None
    wanted = "RESISTANCE" if direction == "CALL" else "SUPPORT"
    candidates = [
        z for z in zones
        if z.kind == wanted and z.is_strong and z.distance_atr <= within_atr
    ]
    return min(candidates, key=lambda z: z.distance_atr) if candidates else None
