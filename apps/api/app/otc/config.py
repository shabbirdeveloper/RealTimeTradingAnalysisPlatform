"""
The single source of configuration for the OTC engine (spec Phase 49).

Every threshold in this file is a HYPOTHESIS, not a finding. They are the
starting parameters the spec proposes, and the whole apparatus downstream
-- rejected-setup capture, score buckets, walk-forward -- exists to
replace them with measured values. Nothing here should be described to a
user as tuned, optimal, or validated until a backtest says so.

WHY ONE FILE
------------
The previous engine spread its thresholds across a StrategyConfig
dataclass, per-asset overrides, a database table, and several module-level
constants. Answering "what score is required right now?" meant reading
four places and knowing which won. That is how the 78 in one module and
the 78 in another drifted apart unnoticed. One file, imported everywhere,
makes the answer a single lookup.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class OTCSymbolConfig:
    """One tradeable instrument. `enabled` is deliberately explicit:
    Phase 1 wants the architecture to support more pairs while exactly one
    of them produces signals, and a disabled entry documents the intent
    better than a commented-out block."""

    symbol: str
    broker: str
    api_symbol: str
    enabled: bool
    expiry_seconds: int = 300


# Exactly one enabled instrument, per Phase 1. The others are declared so
# that adding a pair later is a flag flip plus a backtest, not a refactor.
OTC_SYMBOLS: dict[str, OTCSymbolConfig] = {
    "DERIV_V75": OTCSymbolConfig("DERIV_V75", "DERIV", "R_75", enabled=True),
    "DERIV_V50": OTCSymbolConfig("DERIV_V50", "DERIV", "R_50", enabled=False),
    "DERIV_V25": OTCSymbolConfig("DERIV_V25", "DERIV", "R_25", enabled=False),
}


def enabled_symbols() -> list[str]:
    return [s for s, cfg in OTC_SYMBOLS.items() if cfg.enabled]


@dataclass(frozen=True)
class OTCEngineConfig:
    # --- expiry (Phase 10) -------------------------------------------------
    expiry_seconds: int = 300

    # --- evaluation cadence (Phase 12) -------------------------------------
    # Every closed 30-second bar, not every tick. Ticks produce unstable
    # intrabar decisions that flip before the bar they were computed from
    # even exists.
    evaluation_timeframe: str = "S30"

    # --- thresholds (Phase 23) ---------------------------------------------
    minimum_score: int = 78
    # The gap that separates "directional" from "leaning". CALL 79 / PUT 68
    # clears the score bar and fails this one, which is the intent.
    minimum_directional_difference: int = 18

    # --- cooldown (Phase 26) -----------------------------------------------
    cooldown_seconds: int = 300

    # --- data health (Phase 7) ---------------------------------------------
    # Feed not HEALTHY => no signal. There is no override, and adding one
    # would defeat the only mechanism preventing decisions on stale prices.
    max_tick_age_seconds: int = 30
    max_bar_age_seconds: int = 90
    min_ticks_per_minute: int = 10

    # --- warmup (Phase 24) -------------------------------------------------
    # Below this many bars the indicators are still converging and their
    # values are arithmetic, not evidence.
    min_bars_per_timeframe: int = 60

    # --- strategies (Phase 18) ---------------------------------------------
    strategies: dict[str, bool] = field(
        default_factory=lambda: {
            "trend_pullback": True,
            "momentum_continuation": True,
            "level_rejection": True,
        }
    )


    # --- what reaches Telegram (spec Phase 26) --------------------------
    #
    # Empty means "every strategy", which is the correct DEFAULT precisely
    # because nothing has been measured yet. Narrowing this before the
    # backtest has spoken would be picking a favourite, and a favourite
    # chosen on intuition is how a filter that quietly removes the winning
    # setups gets installed and never questioned.
    #
    # Once otc_backtest.py --sweep shows which strategy carries a lower
    # interval bound above break-even on a usable number of signals, put
    # its name here and only it will notify.
    notify_strategies: tuple[str, ...] = ()

    # Signals below this score are stored but not sent. Separate from
    # minimum_score on purpose: what is worth RECORDING and what is worth
    # INTERRUPTING someone for are different bars, and collapsing them
    # means every loosening of the engine also spams the channel.
    notify_min_score: int = 0


CONFIG = OTCEngineConfig()


@dataclass(frozen=True)
class EngineProfile:
    """Which timeframes an instrument class actually has.

    Broker feeds publish ticks, so sub-minute bars can be built. Public
    quote vendors do not -- Twelve Data's floor is one minute -- so the
    real-market profile has no S30 to time entries on and uses M1 instead.

    This is a profile rather than a runtime `if` because the difference is
    a property of the DATA SOURCE, not of the moment. An engine that asks
    for S30 and quietly proceeds without it would be scoring entry timing
    on evidence it never had, and would report the same confidence for it.
    """

    name: str
    timeframes: tuple[str, ...]
    context: str
    structure: str
    momentum: str
    confirmation: str
    entry: str
    expiry_seconds: int = 300
    evaluation_seconds: int = 30

    @property
    def required(self) -> tuple[str, ...]:
        """Timeframes that must have converged before anything is scored."""
        return (self.context, self.structure, self.momentum, self.confirmation)


# Tick feed available: the full six timeframes of Phase 8.
OTC_PROFILE = EngineProfile(
    name="broker_otc",
    timeframes=("S15", "S30", "M1", "M3", "M5", "M15"),
    context="M15", structure="M5", momentum="M3", confirmation="M1", entry="S30",
    expiry_seconds=300, evaluation_seconds=30,
)

# Quote vendor, one-minute floor. Same five-minute expiry and the same
# strategies; entry timing reads M1 because nothing finer exists. Evaluated
# every five minutes because that is both the provider's practical budget
# and the rate at which the entry bar actually changes.
REAL_MARKET_PROFILE = EngineProfile(
    name="public_market",
    timeframes=("M1", "M3", "M5", "M15"),
    context="M15", structure="M5", momentum="M3", confirmation="M1", entry="M1",
    expiry_seconds=300, evaluation_seconds=300,
)


def profile_for(symbol: str) -> EngineProfile:
    return OTC_PROFILE if symbol in OTC_SYMBOLS else REAL_MARKET_PROFILE

# The six timeframes of Phase 8 and no others, ordered fastest-first to
# match schemas.candle.Timeframe. Each has one job; a seventh would need to
# justify itself against an existing one.
TIMEFRAMES: tuple[str, ...] = ("S15", "S30", "M1", "M3", "M5", "M15")

TIMEFRAME_ROLE: dict[str, str] = {
    "M15": "context",
    "M5": "structure",
    "M3": "momentum",
    "M1": "confirmation",
    "S30": "entry timing",
    "S15": "micro confirmation",
}

TIMEFRAME_SECONDS: dict[str, int] = {
    "S15": 15, "S30": 30, "M1": 60, "M3": 180, "M5": 300, "M15": 900,
}
