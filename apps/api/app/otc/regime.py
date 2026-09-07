"""
Market regime (spec Phase 16), deterministic and explainable.

The old classifier returned three states from H1 candles. That was too
coarse to route anything: TRENDING covered both a clean advance and a
vertical spike, and RANGING covered both an orderly range and chop that
nothing should be traded in. Phase 19 routes strategies by regime, so the
regime has to distinguish cases that call for different strategies --
otherwise routing is decoration.

Deliberately rule-based rather than learned. A regime a human cannot
audit is a regime nobody can debug at 3am, and Phase 45 rules out ML
until the deterministic path has been shown to carry an edge.
"""

from __future__ import annotations

from app.otc.config import OTC_PROFILE, EngineProfile
from app.otc.features import MarketContext, TimeframeFeatures

TRENDING_UP = "TRENDING_UP"
TRENDING_DOWN = "TRENDING_DOWN"
RANGING = "RANGING"
BREAKOUT = "BREAKOUT"
PULLBACK = "PULLBACK"
HIGH_VOLATILITY = "HIGH_VOLATILITY"
LOW_VOLATILITY = "LOW_VOLATILITY"
CHOPPY = "CHOPPY"
UNKNOWN = "UNKNOWN"

# Regimes in which no strategy is permitted to fire (Phase 19).
NO_TRADE_REGIMES = frozenset({CHOPPY, UNKNOWN})

# EMA separation, in ATRs, above which the fast/slow pair counts as spread.
_TREND_SEPARATION = 0.35
# ATR percentile bounds for "the market is moving unusually much/little".
_HIGH_VOL_PCT = 85.0
_LOW_VOL_PCT = 15.0


def classify(context: MarketContext, profile: EngineProfile = OTC_PROFILE) -> tuple[str, str]:
    """Return (regime, one-line reason). The reason is stored with every
    decision so a rejected setup can be explained months later without
    re-deriving it."""
    structure = context.frame(profile.structure)
    momentum = context.frame(profile.momentum)

    if structure is None or not structure.ready:
        return UNKNOWN, f"{profile.structure} features have not converged"

    # Volatility first: an extreme reading overrides directional reads,
    # because a strategy calibrated for normal range behaves differently
    # when the range has tripled.
    if structure.atr_pct is not None:
        if structure.atr_pct >= _HIGH_VOL_PCT:
            return HIGH_VOLATILITY, f"{profile.structure} ATR in the {structure.atr_pct:.0f}th percentile"
        if structure.atr_pct <= _LOW_VOL_PCT:
            return LOW_VOLATILITY, f"{profile.structure} ATR in the {structure.atr_pct:.0f}th percentile"

    sep = structure.ema_separation
    seq = structure.structure.sequence
    bos = structure.structure.bos

    # Chop: the EMAs are entangled AND structure has no sequence. Either
    # alone is ordinary; together they mean there is nothing to read.
    if sep is not None and abs(sep) < 0.12 and seq in (None, "MIXED"):
        return CHOPPY, "EMAs entangled with no structural sequence"

    if sep is None or seq is None:
        return UNKNOWN, f"insufficient structure or EMA data on {profile.structure}"

    trending_up = sep >= _TREND_SEPARATION and seq == "HH_HL"
    trending_down = sep <= -_TREND_SEPARATION and seq == "LH_LL"

    if trending_up or trending_down:
        direction = TRENDING_UP if trending_up else TRENDING_DOWN
        # A break of structure in the trend's own direction, with momentum
        # confirming, is an expansion rather than a continuation -- and the
        # two want different strategies.
        if bos and _momentum_agrees(momentum, up=trending_up):
            return BREAKOUT, f"{profile.structure} {seq} with break of structure and {profile.momentum} momentum agreeing"
        # Price back inside the fast EMA while the trend structure holds is
        # the pullback the trend-continuation strategy is built for.
        pull = structure.price_vs_ema21
        if pull is not None and ((trending_up and pull < 0.2) or (trending_down and pull > -0.2)):
            return PULLBACK, f"{profile.structure} {seq} with price retraced to EMA21"
        return direction, f"{profile.structure} {seq}, EMA separation {sep:+.2f} ATR"

    if seq == "MIXED" or abs(sep) < _TREND_SEPARATION:
        return RANGING, f"no sustained direction on {profile.structure} (separation {sep:+.2f} ATR)"

    return UNKNOWN, "regime rules did not match"


def _momentum_agrees(frame: TimeframeFeatures | None, *, up: bool) -> bool:
    if frame is None or frame.macd_hist is None:
        return False
    return frame.macd_hist > 0 if up else frame.macd_hist < 0
