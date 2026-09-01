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
    suspicious = []
    for asset in assets:
        loaded = load_history(asset, start, end)
        counts = {tf: len(bars) for tf, bars in loaded.items()}
        m5 = counts.get("M5", 0)
        print(f"  {asset.value:<8} {m5:>6} M5   "
              f"{counts.get('M15', 0):>5} M15   {counts.get('H1', 0):>5} H1   "
              f"{counts.get('H4', 0):>4} H4")
        # A count sitting exactly on a page boundary is the signature of a
        # truncated read, not of history that happened to end there. This
        # already cost one sweep: 15,000 stored bars came back as 1,000, every
        # decision hit "insufficient history", and the run printed a clean
        # table of zeroes that read like a finding about the strategy.
        if m5 and m5 % 1000 == 0:
            suspicious.append(f"{asset.value} ({m5})")
        if m5:
            history[asset.value] = loaded

    if suspicious:
        print(f"\n  WARNING: exact multiples of 1000 bars for {', '.join(suspicious)}.")
        print("  That is the shape of a capped query, not of real history. Results below")
        print("  may be measuring a truncated read rather than your data.")

    if not history:
        print("\nNo history in that window. Run backfill.py --run first.")
        sys.exit(1)

    # ONE replay, not one per threshold.
    #
    # The threshold only decides whether a scored setup is accepted; it does
    # not change the score, the direction, the chosen expiry or the outcome.
    # (`best` is the highest-scoring eligible candidate, and the highest
    # scorer is the same candidate whenever it clears at all.) So replaying
    # per threshold recomputed identical decisions eight times over -- and a
    # 14-day sweep was slow enough to have to be interrupted.
    #
    # Replay once at a floor of 1, then count how many of those opportunities
    # each threshold would have taken. Identical results, an eighth of the work.
    print("\nReplaying once, then applying each threshold to the result...")
    summary = run_backtest(
        history, start=start, end=end,
        technical_score_threshold=1, step_minutes=args.step,
    )
    scored = [o for o in summary.opportunities if o.technical_score > 0]
    print(f"{len(scored)} scored setups found.\n")

    if not scored:
        print("No directional setups at all in this window. That is a finding about")
        print("the timeframe-agreement rule, not about the threshold: nothing ever")
        print("reached the scoring stage.\n")
        return

    top = max(o.technical_score for o in scored)
    print(f"{'thresh':>7} {'setups':>7} {'taken':>7} {'share':>7} "
          f"{'W':>5} {'L':>5} {'win rate':>9} {'95% interval':>16}  verdict")
    print("-" * 88)

    breakeven = 100 / (1 + PAYOUT)
    for threshold in THRESHOLDS:
        taken_all = [o for o in scored if o.technical_score >= threshold]
        wins = sum(1 for o in taken_all if o.result == "WON")
        losses = sum(1 for o in taken_all if o.result == "LOST")
        resolved = wins + losses
        share = 100 * len(taken_all) / len(scored)
        marker = " *" if threshold == 78 else "  "

        if resolved == 0:
            why = "nothing scored this high" if not taken_all else "none resolved yet"
            print(f"{threshold:>7}{marker}{len(scored):>5} {len(taken_all):>7} {share:>6.1f}% "
                  f"{'—':>5} {'—':>5} {'—':>9} {'—':>16}  {why}")
            continue

        rate = 100 * wins / resolved
        lo, hi = wilson(wins, resolved)

        # The verdict reads the LOWER bound against break-even. A point
        # estimate above it proves nothing when the interval spans it.
        if resolved < 30:
            verdict = "sample too small"
        elif lo > breakeven:
            verdict = "profitable at 80% payout"
        elif hi < breakeven:
            verdict = "LOSES at 80% payout"
        else:
            verdict = "indistinguishable from break-even"

        print(f"{threshold:>7}{marker}{len(scored):>5} {len(taken_all):>7} {share:>6.1f}% "
              f"{wins:>5} {losses:>5} {rate:>8.1f}% "
              f"{lo:>6.1f}-{hi:<6.1f}  {verdict}")

    print("-" * 88)
    print(f"  * = the threshold the engine is running now")
    print(f"  Break-even at an {PAYOUT:.0%} payout is {breakeven:.1f}%. Anything below that")
    print(f"  loses money no matter how good the win rate looks next to 50%.")
    print()
    print(f"  Highest score anything reached in this window: {top}/100.")
    print()
    print("  Judge a row by whether its LOWER interval bound clears break-even, not by")
    print("  its win rate. Fewer than ~30 resolved signals cannot show anything either way,")
    print("  and a high win rate on 8 trades is the single most common way to fool yourself.")


if __name__ == "__main__":
    main()
