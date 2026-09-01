"""
How often would this engine actually have fired, and would it have been right?

WHY THIS EXISTS
---------------
The live dashboard shows NO TRADE on every card, and that has two possible
meanings that look identical from the outside:

  * the market genuinely offers nothing right now, or
  * the rules are so strict that they would reject almost anything.

Watching live cannot separate those -- you would need weeks. But 17 days of
real M5 history is already backfilled, and the backtester replays it with no
look-ahead, so the question is answerable in minutes instead.

Sweeps the technical-score threshold and reports, for each value: how many
setups it would have accepted, and what share of them won.

    .venv\\Scripts\\python.exe sweep.py
    .venv\\Scripts\\python.exe sweep.py --days 14 --step 15

READ THE OUTPUT CAREFULLY
-------------------------
A threshold that wins more often on fewer trades is not automatically better:
at some point the sample gets too small to mean anything, and the win rates
become noise. The 95% interval printed alongside each row is what tells you
whether a difference is real. A row with 6 signals is not evidence.

This is measurement, not tuning. Nothing here changes the running engine.
"""
from __future__ import annotations

import argparse
import math
import sys
from datetime import datetime, timedelta, timezone

from app.backtesting.engine import run_backtest
from app.backtesting.repository import load_history
from app.schemas.candle import Asset

THRESHOLDS = (55, 60, 65, 70, 74, 78, 82, 86)
# Payout on a typical binary contract. Below this win rate the strategy
# loses money however good it looks -- an 80% payout needs 55.6% just to
# break even, which is the number that actually matters.
PAYOUT = 0.80


def wilson(wins: int, total: int) -> tuple[float, float]:
    """95% confidence interval for a win rate. A point estimate from 8
    trades and one from 800 look identical without this."""
    if total == 0:
        return (0.0, 0.0)
    z, p, n = 1.96, wins / total, total
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, (centre - margin) * 100), min(100.0, (centre + margin) * 100))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=14, help="how far back to replay")
    parser.add_argument("--step", type=int, default=15,
                        help="minutes between decision points; 5 is thorough, 15 is ~3x faster")
    args = parser.parse_args()

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=args.days)
    assets = list(Asset)

    print(f"\nReplaying {args.days} days x {len(assets)} assets, "
          f"a decision every {args.step} minutes.")
    print("No look-ahead: each decision sees only candles closed at that moment.\n")

    history = {}
    for asset in assets:
        loaded = load_history(asset, start, end)
        bars = len(loaded.get("M5", []))
        print(f"  {asset.value:<8} {bars:>6} M5 bars")
        if bars:
            history[asset.value] = loaded

    if not history:
        print("\nNo history in that window. Run backfill.py --run first.")
        sys.exit(1)

    print(f"\n{'thresh':>7} {'setups':>7} {'taken':>7} {'share':>7} "
          f"{'W':>5} {'L':>5} {'win rate':>9} {'95% interval':>16}  verdict")
    print("-" * 88)

    breakeven = 100 / (1 + PAYOUT)
    for threshold in THRESHOLDS:
        summary = run_backtest(
            history, start=start, end=end,
            technical_score_threshold=threshold, step_minutes=args.step,
        )
        taken = summary.accepted_signals
        resolved = summary.wins + summary.losses
        share = 100 * taken / summary.total_opportunities if summary.total_opportunities else 0.0

        if resolved == 0:
            print(f"{threshold:>7} {summary.total_opportunities:>7} {taken:>7} {share:>6.1f}% "
                  f"{'—':>5} {'—':>5} {'—':>9} {'—':>16}  nothing resolved")
            continue

        rate = 100 * summary.wins / resolved
        lo, hi = wilson(summary.wins, resolved)

        # The only verdict that matters: is the LOWER bound above break-even?
        # A point estimate above it proves nothing when the interval spans it.
        if resolved < 30:
            verdict = "sample too small"
        elif lo > breakeven:
            verdict = "profitable at 80% payout"
        elif hi < breakeven:
            verdict = "LOSES at 80% payout"
        else:
            verdict = "indistinguishable from break-even"

        marker = " *" if threshold == 78 else "  "
        print(f"{threshold:>7}{marker}{summary.total_opportunities:>5} {taken:>7} {share:>6.1f}% "
              f"{summary.wins:>5} {summary.losses:>5} {rate:>8.1f}% "
              f"{lo:>6.1f}-{hi:<6.1f}  {verdict}")

    print("-" * 88)
    print(f"  * = the threshold the engine is running now")
    print(f"  Break-even at an {PAYOUT:.0%} payout is {breakeven:.1f}%. Anything below that")
    print(f"  loses money no matter how good the win rate looks next to 50%.")
    print()
    print("  Judge a row by whether its LOWER interval bound clears break-even, not by")
    print("  its win rate. Fewer than ~30 resolved signals cannot show anything either way,")
    print("  and a high win rate on 8 trades is the single most common way to fool yourself.")


if __name__ == "__main__":
    main()
