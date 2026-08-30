"""
Instrument safety guard: real markets only, never broker-synthetic ones.

WHY THIS EXISTS
---------------
This platform analyses REAL market data (Twelve Data) and the user
manually places the trade on Quotex. That only produces a meaningful
result when the thing analysed and the thing traded are the same price
series.

Binary brokers also offer "OTC" instruments -- e.g. "EUR/USD (OTC)" --
which are available 24/7, including weekends when the real market is
shut. Those are NOT the real market. They are synthetic series generated
by the broker, which does not publish how the values are derived.

So applying this platform's analysis to an OTC instrument is not
"slightly less accurate". The analysis and the settlement price are
unrelated series, while the signal still renders as a confident, graded
result. That is the single most dangerous failure this system could
produce: it looks exactly like a real signal.

The project spec also forbids obtaining broker-side prices (no scraping,
no undocumented Quotex API), so there is no honest way to analyse OTC
instruments at all. The correct behaviour is therefore to refuse them
outright rather than degrade quietly.

This module is the enforcement point. It is deliberately conservative:
anything that even looks like an OTC/synthetic instrument is rejected,
because a false rejection costs one configuration fix while a false
acceptance costs real money on a signal that never meant anything.
"""
from __future__ import annotations

import re

# Matches the ways brokers commonly label synthetic instruments:
#   "EURUSD-OTC", "EUR/USD (OTC)", "EURUSD_otc", "EURUSD OTC",
#   plus other synthetic families some brokers expose.
_OTC_PATTERNS = (
    re.compile(r"\bOTC\b", re.IGNORECASE),
    re.compile(r"[-_ ]OTC", re.IGNORECASE),
    re.compile(r"\bSYNTHETIC\b", re.IGNORECASE),
    re.compile(r"\bVOLATILITY\s*\d+", re.IGNORECASE),  # e.g. "Volatility 75 Index"
    re.compile(r"\bBOOM\s*\d+|\bCRASH\s*\d+", re.IGNORECASE),
)


class SyntheticInstrumentError(ValueError):
    """Raised when a broker-synthetic instrument reaches the analysis path."""


def is_synthetic_symbol(symbol: str) -> bool:
    """True if `symbol` looks like a broker-generated instrument rather
    than a real market. See the module docstring for why this is refused
    rather than handled."""
    if not symbol:
        return False
    return any(pattern.search(symbol) for pattern in _OTC_PATTERNS)


def assert_real_market_symbol(symbol: str) -> None:
    """Guard called before any analysis or signal write.

    Raises rather than returning a flag on purpose: a caller that forgets
    to check a boolean fails open, and failing open here means emitting a
    confident signal about a price series the user isn't actually trading.
    """
    if is_synthetic_symbol(symbol):
        raise SyntheticInstrumentError(
            f"{symbol!r} looks like a broker-synthetic/OTC instrument. This platform "
            "analyses real market data only — its analysis is meaningless against a "
            "broker-generated price series, and the project explicitly does not source "
            "broker-side prices. Trade the real-market symbol during real market hours, "
            "or use a genuinely 24/7 real market such as crypto."
        )

# ---------------------------------------------------------------------------
# Instrument class (real markets only -- synthetic ones are refused above)
# ---------------------------------------------------------------------------
# Kept here rather than next to the pydantic `Asset` enum so that the market
# hours logic, which depends on this, stays importable and unit-testable with
# no third-party packages installed.
#
# Symbols are compared as plain strings; `Asset` is a `str` Enum, so passing
# an Asset member works directly.

CRYPTO_SYMBOLS: frozenset[str] = frozenset({"BTCUSD", "ETHUSD"})


def is_crypto_symbol(symbol: str) -> bool:
    """True for continuously-traded crypto markets (24/7/365), False for
    forex and metals, which follow the forex week."""
    return str(symbol).upper() in CRYPTO_SYMBOLS
