"""
The win/loss rule (spec section 49).

One function, in one place, deliberately. It is used by three callers that
must agree exactly:

  * live resolution of accepted signals
  * shadow resolution of rejected opportunities (the counterfactual)
  * the historical backtester

If these ever diverged, the comparisons the whole platform is built on would
be meaningless: a backtest could not be compared to live results, and a
rejected setup could not be compared to an accepted one. Kept free of any
database import so it can be unit-tested directly.
"""
from __future__ import annotations


def outcome(direction: str, entry_price: float, closing_price: float) -> str:
    """WON / LOST / DRAW for a binary directional trade.

    Equal entry and closing price is a DRAW for both directions. Spec section
    49 leaves the equal-price rule configurable; this is the least surprising
    default, and matching it across all three callers matters more than the
    specific choice.
    """
    if direction not in ("CALL", "PUT"):
        raise ValueError(f"outcome() expects CALL or PUT, got {direction!r}")
    if closing_price == entry_price:
        return "DRAW"
    if direction == "CALL":
        return "WON" if closing_price > entry_price else "LOST"
    return "WON" if closing_price < entry_price else "LOST"
