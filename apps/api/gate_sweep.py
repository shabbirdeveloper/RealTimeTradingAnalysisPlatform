"""
Would loosening the multi-timeframe gate produce anything worth trading?

WHY THIS EXISTS
---------------
Across the live log, roughly 40% of every timeframe's reads were NEUTRAL,
and 38 of 84 decisions scored exactly zero -- they never reached scoring
at all. A NEUTRAL vote can never agree with anything, and the gate needs
three of four timeframes pointing the same way, so the engine is stopped
at its first substantive test far more often than at the quality bar.

Two numbers control that, and neither has ever been measured:

  min_bias_votes         how many of a timeframe's five voters must agree
                         before that timeframe commits to a direction
  min_timeframe_agreement  how many timeframes must then point the same way
  min_score_difference   how far the CALL score must beat the PUT score
                         before either is acted on

Loosening them would obviously produce more signals. The only question
worth asking is whether those extra signals win often enough to pay for
themselves, and that is what this measures.

    .venv\\Scripts\\python.exe gate_sweep.py
    .venv\\Scripts\\python.exe gate_sweep.py --days 14 --step 30

READ THE OUTPUT CAREFULLY
-------------------------
More signals at a similar win rate is not an improvement -- at an 80%
payout it is a faster way to lose. The verdict column reads the LOWER
bound of the 95% interval against break-even, so a row only says
"profitable" when the evidence actually supports it. Rows with few
resolved trades will say "too few", and that is the honest answer.

This is measurement, not tuning. Nothing here changes the running engine.
"""
from __future__ import annotations

import argparse
import math
import sys
from datetime import datetime, timedelta, timezone

from app.backtesting.engine import run_backtest
from app.backtesting.repository import load_history
from app.features.strategy import default_strategy
from app.instruments import get_instrument
from app.schemas.candle import Asset

PAYOUT = 0.80
MIN_RESOLVED = 30


def wilson(wins: int, total: int) -> tuple[float, float]:
    if total == 0:
        return (0.0, 0.0)
    z, p, n = 1.96, wins / total, total
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    m = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, (c - m) * 100), min(100.0, (c + m) * 100))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=14)
    parser.add_argument("--step", type=int, default=30,
                        help="minutes between decision points; this sweep replays "
                             "once per combination, so keep it coarse")
    parser.add_argument("--threshold", type=int, default=1,
                        help="score floor while measuring the gates; 1 isolates the "
                             "gate's effect from the quality bar's")
    args = parser.parse_args()

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=args.days)

    history = {}
    for asset in Asset:
        loaded = load_history(asset, start, end)
        m5 = len(loaded.get("M5", []))
        if m5 and m5 % 1000 == 0:
            print(f"  WARNING: {asset.value} returned exactly {m5} bars -- "
                  "that is the shape of a capped query, not real history.")
        if m5:
            history[asset.value] = loaded
            print(f"  {asset.value:<8} {m5:>6} M5 bars")

    if not history:
        print("\nNo history in that window. Run backfill.bat first.")
        sys.exit(1)

    combos = [
        (votes, agree, sep)
        for votes in (1, 2, 3)
        for agree in (2, 3, 4)
        for sep in (0, 20, 40)
    ]
    print(f"\nReplaying {args.days} days x {len(history)} assets, "
          f"{len(combos)} gate combinations, a decision every {args.step} minutes.")
    print("No look-ahead: each decision sees only candles closed at that moment.")
    print("This takes a while -- it is a full replay per combination.\n")

    print(f"{'votes':>5} {'agree':>6} {'sep':>4} {'setups':>7} {'taken':>6} "
          f"{'W':>5} {'L':>5} {'win rate':>9} {'95% interval':>16}  verdict")
    print("-" * 90)

    breakeven = 100 / (1 + PAYOUT)
    current = None

    for votes, agree, sep in combos:
        def strategy_for(asset: str, _v=votes, _a=agree, _s=sep):
            profile = get_instrument(asset).profile
            return default_strategy(asset, expiries=profile.expiries_seconds).with_gates(
                agreement=_a, bias_votes=_v, score_difference=_s,
            )

        summary = run_backtest(
            history, start=start, end=end,
            technical_score_threshold=args.threshold,
            step_minutes=args.step,
            strategy_for=strategy_for,
        )
        scored = [o for o in summary.opportunities if o.technical_score > 0]
        taken = [o for o in scored if o.accepted]
        wins = sum(1 for o in taken if o.result == "WON")
        losses = sum(1 for o in taken if o.result == "LOST")
        resolved = wins + losses

        if resolved == 0:
            verdict, rate_text, interval_text = "nothing resolved", "--", "--"
        else:
            rate = 100 * wins / resolved
            low, high = wilson(wins, resolved)
            rate_text = f"{rate:.1f}%"
            interval_text = f"{low:.1f}-{high:.1f}"
            if resolved < MIN_RESOLVED:
                verdict = f"too few ({resolved})"
            elif low > breakeven:
                verdict = "BEATS break-even"
            elif high < breakeven:
                verdict = "loses at 80% payout"
            else:
                verdict = "indistinguishable"

        marker = " <- current" if (votes, agree, sep) == (2, 3, 0) else ""
        print(f"{votes:>5} {agree:>6} {sep:>4} {len(scored):>7} {len(taken):>6} "
              f"{wins:>5} {losses:>5} {rate_text:>9} {interval_text:>16}  {verdict}{marker}")
        if (votes, agree, sep) == (2, 3, 0):
            current = (len(taken), wins, resolved)

    print(f"\nBreak-even at an {PAYOUT:.0%} payout is {breakeven:.1f}%.")
    print("The verdict reads the LOWER bound of the interval, so a row claims")
    print("nothing the evidence does not support.\n")
    if current:
        print(f"Your current gate (2 votes, 3 of 4, no separation floor) took {current[0]} setups, "
              f"{current[2]} resolved.\n")
    print("A row with more signals at the same win rate is NOT an improvement --")
    print("at an 80% payout it is a faster way to lose. Only a row whose lower")
    print("bound clears break-even is worth changing the engine for.\n")


if __name__ == "__main__":
    main()
