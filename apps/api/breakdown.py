"""
Where the losses actually come from.

WHY THIS EXISTS
---------------
With the backtester's expiry unit fixed, the threshold sweep returned a
win rate of 46-48% across every threshold on ~1,500 resolved trades, with
95% intervals that at several thresholds exclude 50%. That is not "no
edge". A coin flip does not reliably land below half.

Two very different things produce that number, and the sweep cannot tell
them apart:

  1. A genuine inverse relationship -- the features really do lean the
     wrong way for this horizon.
  2. One regime, or one asset, or a few days, dragging a neutral system
     under water.

The distinction decides everything that follows, so this splits the same
replay every way the data allows and reports each slice with its own
interval.

ABOUT INVERTING
---------------
"Losing 46% of the time means flipping it wins 54%" is the oldest trap in
backtesting, and it is wrong twice over here. 54% is still below the
55.6% needed to break even at an 80% payout, so an inverted strategy also
loses money -- just more slowly. And a tilt measured in one 14-day window
is exactly what a single regime looks like from the inside. Nothing here
recommends inverting anything.

    .venv\\Scripts\\python.exe breakdown.py
    .venv\\Scripts\\python.exe breakdown.py --days 14 --threshold 55
"""
from __future__ import annotations

import argparse
import math
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from app.backtesting.engine import run_backtest
from app.backtesting.repository import load_history
from app.schemas.candle import Asset

PAYOUT = 0.80
BREAK_EVEN = 100 / (1 + PAYOUT)
MIN_MEANINGFUL = 30


def wilson(wins: int, total: int) -> tuple[float, float]:
    if total == 0:
        return (0.0, 0.0)
    z, p, n = 1.96, wins / total, total
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    m = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, (c - m) * 100), min(100.0, (c + m) * 100))


def verdict(wins: int, losses: int) -> str:
    n = wins + losses
    if n == 0:
        return "nothing resolved"
    if n < MIN_MEANINGFUL:
        return f"too few ({n})"
    low, high = wilson(wins, n)
    if low > BREAK_EVEN:
        return "BEATS break-even"
    if high < 50.0:
        # The interesting one: reliably worse than chance is a real
        # measurement, not an absence of one.
        return "worse than chance"
    if low > 50.0:
        return "better than chance, below break-even"
    return "indistinguishable from chance"


def report(title: str, rows: dict[str, tuple[int, int]]) -> None:
    print(f"\n{title}")
    print(f"  {'slice':<22} {'n':>6} {'W':>5} {'L':>5} {'rate':>7} {'95% interval':>15}  verdict")
    print("  " + "-" * 86)
    for key in sorted(rows, key=lambda k: -(rows[k][0] + rows[k][1])):
        wins, losses = rows[key]
        n = wins + losses
        if n == 0:
            continue
        rate = 100 * wins / n
        low, high = wilson(wins, n)
        print(f"  {key[:22]:<22} {n:>6} {wins:>5} {losses:>5} {rate:>6.1f}% "
              f"{low:>6.1f}-{high:<8.1f} {verdict(wins, losses)}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=14)
    parser.add_argument("--step", type=int, default=15)
    parser.add_argument("--threshold", type=int, default=1,
                        help="score floor; 1 uses every scored setup, which is the "
                             "largest sample and the least self-selected")
    args = parser.parse_args()

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=args.days)

    history = {}
    for asset in Asset:
        loaded = load_history(asset, start, end)
        if loaded.get("M5"):
            history[asset.value] = loaded
    if not history:
        print("No history in that window. Run backfill.bat first.")
        sys.exit(1)

    print(f"\nReplaying {args.days} days x {len(history)} assets, every {args.step} minutes, "
          f"score floor {args.threshold}.")
    summary = run_backtest(
        history, start=start, end=end,
        technical_score_threshold=args.threshold, step_minutes=args.step,
    )
    taken = [o for o in summary.opportunities
             if o.accepted and o.result in ("WON", "LOST")]
    if not taken:
        print("Nothing resolved in that window.")
        return

    wins = sum(1 for o in taken if o.result == "WON")
    losses = len(taken) - wins
    low, high = wilson(wins, len(taken))
    print(f"\nOVERALL  {len(taken)} resolved · {wins}W / {losses}L · "
          f"{100 * wins / len(taken):.1f}%  ({low:.1f}-{high:.1f})  {verdict(wins, losses)}")
    print(f"Break-even at an {PAYOUT:.0%} payout is {BREAK_EVEN:.1f}%.")

    def group(keyfn) -> dict[str, tuple[int, int]]:
        out: dict[str, list[int]] = defaultdict(lambda: [0, 0])
        for o in taken:
            bucket = out[str(keyfn(o))]
            bucket[0 if o.result == "WON" else 1] += 1
        return {k: (v[0], v[1]) for k, v in out.items()}

    report("BY ASSET", group(lambda o: o.asset))
    report("BY MARKET REGIME", group(lambda o: o.market_regime))
    report("BY SESSION", group(lambda o: o.session))
    report("BY DIRECTION", group(lambda o: o.direction))
    report("BY EXPIRY", group(lambda o: f"{o.expiry_seconds}s"))
    report("BY SCORE BAND", group(lambda o: f"{o.technical_score // 10 * 10}-{o.technical_score // 10 * 10 + 9}"))
    # The poor man's walk-forward: is this one bad week or a steady tilt?
    report("BY DAY", group(lambda o: o.generated_at.strftime("%a %d %b")))

    print("""
HOW TO READ THIS

  A slice that is 'worse than chance' with a large n is a real measurement:
  the features lean the wrong way for this horizon in this window. A slice
  that is 'indistinguishable' is telling you nothing, whatever its rate.

  The question BY DAY answers: if most days sit near 50% and two are
  catastrophic, this is a regime artifact and the engine is roughly neutral.
  If almost every day is under 50%, the tilt is systematic.

  Do NOT invert the strategy on this evidence. Inverting a 46% system gives
  54%, which is still below the 55.6% needed to break even at an 80% payout
  -- and a tilt measured in a single window is what one regime looks like
  from the inside.
""")


if __name__ == "__main__":
    main()
