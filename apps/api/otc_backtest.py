"""
Backtest the 5-minute engine over stored history.

WHY THIS EXISTS
---------------
"How can we trade like this, there is no result" is the right question,
and until now nothing could answer it. The dashboard shows what the
engine decided in the last few minutes; it cannot say how many signals a
day this engine produces, or whether those signals win.

That is the only pair of numbers that decides whether the platform is
usable:

    signals per day   -- is there anything to trade at all?
    win rate + interval -- would trading them make or lose money?

Both come from replaying the SAME evaluate() over bars that are already
stored, so no provider quota is spent and the answer is available in
seconds rather than after weeks of forward testing.

NO LOOKAHEAD
------------
At simulated time T the engine is handed only bars that had CLOSED by T,
sliced from the stored series exactly the way the live collector slices
them. The outcome is then read from a bar AFTER T + expiry, which is the
only place future data is allowed to appear.

WHAT IT WILL NOT DO
-------------------
It will not tell you the engine works. A win rate measured on one stretch
of one instrument is a description of that stretch. The interval is
printed for exactly that reason: read the LOWER bound against break-even,
never the headline.

    .venv\\Scripts\\python.exe otc_backtest.py
    .venv\\Scripts\\python.exe otc_backtest.py --symbol EURUSD --days 5
    .venv\\Scripts\\python.exe otc_backtest.py --sweep
"""
from __future__ import annotations

import argparse
import math
import sys
from datetime import datetime, timedelta, timezone

from app.otc.config import CONFIG, TIMEFRAME_SECONDS, profile_for
from app.otc.engine import evaluate
from app.otc.health import FeedStatus, MarketDataHealth

# Storage import is deferred into load(): the replay RULES below -- the
# no-lookahead slice, the outcome test, the interval -- are pure, and they
# are the part most worth testing. Requiring a database client to import
# them would make the one thing that must be provably correct the one
# thing hardest to test.

# Payout assumptions. 80% is the conservative default; Quotex quoted 91%
# on EUR/USD when this was written, so both are reported -- the difference
# moves break-even by three points and can flip a verdict.
PAYOUTS = (0.80, 0.91)


def break_even(payout: float) -> float:
    return 100.0 / (1.0 + payout)


def wilson(wins: int, total: int) -> tuple[float, float]:
    if total == 0:
        return (0.0, 100.0)
    z = 1.96
    p = wins / total
    d = 1 + z * z / total
    centre = (p + z * z / (2 * total)) / d
    margin = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / d
    return (max(0.0, (centre - margin) * 100), min(100.0, (centre + margin) * 100))


def healthy_at(when: datetime) -> MarketDataHealth:
    """Replay assumes a healthy feed. The live engine refuses to signal on
    an unhealthy one, so including unhealthy periods here would measure the
    feed rather than the strategies -- and those failures are already
    counted separately by the collector."""
    return MarketDataHealth(
        symbol="replay", status=FeedStatus.HEALTHY, last_tick_at=when,
        latency_ms=None, ticks_per_minute=30.0,
        duplicate_ticks=0, rejected_ticks=0, reason="replay",
    )


def load(symbol: str, timeframes: tuple[str, ...], days: int) -> dict[str, list[dict]]:
    from app.storage.candle_repository import fetch_recent_otc_candles

    series: dict[str, list[dict]] = {}
    for timeframe in timeframes:
        seconds = TIMEFRAME_SECONDS[timeframe]
        # Enough bars to cover the window plus the engine's warm-up.
        needed = int(days * 86400 / seconds) + CONFIG.min_bars_per_timeframe + 60
        rows = fetch_recent_otc_candles(symbol, timeframe, min(needed, 5000))
        if rows:
            series[timeframe] = rows
    return series


def slice_closed(rows: list[dict], at: datetime, seconds: int) -> list[dict]:
    """Only bars whose window had ENDED by `at` -- the live rule, applied
    identically here. A bar still forming at T is invisible at T."""
    cutoff = at - timedelta(seconds=seconds)
    return [r for r in rows if r["open_time"] <= cutoff]


def outcome(rows: list[dict], entry_at: datetime, entry: float, direction: str,
            expiry_seconds: int) -> str | None:
    """WIN / LOSS / DRAW, or None when no bar covers the expiry instant.

    None is not a loss. An outcome that cannot be observed is not one the
    engine got wrong, and counting it as a loss corrupts the rate downward
    just as surely as dropping losses would corrupt it upward.
    """
    target = entry_at + timedelta(seconds=expiry_seconds)
    after = [r for r in rows if r["open_time"] >= target]
    if not after:
        return None
    close = float(after[0]["close"])
    if close == entry:
        return "DRAW"
    higher = close > entry
    return "WIN" if (higher if direction == "CALL" else not higher) else "LOSS"


def run(symbol: str, days: int, threshold: int, separation: int, step_seconds: int) -> dict:
    profile = profile_for(symbol)
    series = load(symbol, profile.timeframes, days)

    missing = [tf for tf in profile.required if tf not in series]
    if missing:
        return {"error": f"no stored candles for {', '.join(missing)}"}

    entry_rows = series[profile.entry]
    if len(entry_rows) < 50:
        return {"error": f"only {len(entry_rows)} {profile.entry} bars stored"}

    # Original thresholds restored afterwards -- a sweep must not leave the
    # live engine configured by whatever the last iteration happened to try.
    original = (CONFIG.minimum_score, CONFIG.minimum_directional_difference)
    object.__setattr__(CONFIG, "minimum_score", threshold)
    object.__setattr__(CONFIG, "minimum_directional_difference", separation)

    try:
        start = entry_rows[0]["open_time"] + timedelta(
            seconds=CONFIG.min_bars_per_timeframe * TIMEFRAME_SECONDS[profile.context]
        )
        end = entry_rows[-1]["open_time"]
        if start >= end:
            return {"error": "not enough history for the warm-up window"}

        evaluations = signals = wins = losses = draws = unresolved = 0
        blocked: dict[str, int] = {}
        by_direction = {"CALL": [0, 0], "PUT": [0, 0]}

        at = start
        while at <= end:
            sliced = {
                tf: slice_closed(rows, at, TIMEFRAME_SECONDS[tf])
                for tf, rows in series.items()
            }
            if all(len(v) >= CONFIG.min_bars_per_timeframe for k, v in sliced.items()
                   if k in profile.required):
                evaluations += 1
                decision = evaluate(symbol, sliced, at, healthy_at(at), profile)
                if decision.is_signal:
                    signals += 1
                    result = outcome(entry_rows, at, decision.price,
                                     decision.direction.value, decision.expiry_seconds)
                    if result == "WIN":
                        wins += 1
                        by_direction[decision.direction.value][0] += 1
                    elif result == "LOSS":
                        losses += 1
                    elif result == "DRAW":
                        draws += 1
                    else:
                        unresolved += 1
                    if result in ("WIN", "LOSS"):
                        by_direction[decision.direction.value][1] += 1
                else:
                    key = (decision.rejection_reasons or ["unspecified"])[0]
                    key = "".join("N" if c.isdigit() else c for c in key)
                    blocked[key] = blocked.get(key, 0) + 1
            at += timedelta(seconds=step_seconds)
    finally:
        object.__setattr__(CONFIG, "minimum_score", original[0])
        object.__setattr__(CONFIG, "minimum_directional_difference", original[1])

    span_days = max((end - start).total_seconds() / 86400, 1e-9)
    return {
        "symbol": symbol, "threshold": threshold, "separation": separation,
        "span_days": span_days, "evaluations": evaluations, "signals": signals,
        "wins": wins, "losses": losses, "draws": draws, "unresolved": unresolved,
        "blocked": blocked, "by_direction": by_direction,
    }


def report(r: dict) -> None:
    if r.get("error"):
        print(f"  {r['error']}")
        return

    decided = r["wins"] + r["losses"]
    per_day = r["signals"] / r["span_days"]
    print(f"  window            {r['span_days']:.1f} days")
    print(f"  evaluations       {r['evaluations']}")
    print(f"  signals           {r['signals']}  ({per_day:.1f} per day)")
    print(f"  unresolved        {r['unresolved']}  (no bar at expiry — not counted as losses)")
    print(f"  W / L / D         {r['wins']} / {r['losses']} / {r['draws']}")

    if decided == 0:
        print("\n  No resolved trades. Nothing can be concluded about accuracy.")
        return

    rate = r["wins"] / decided * 100
    low, high = wilson(r["wins"], decided)
    print(f"  win rate          {rate:.1f}%   95% CI {low:.1f}–{high:.1f}%")
    print()
    for payout in PAYOUTS:
        be = break_even(payout)
        if low > be:
            verdict = "PROFITABLE at this payout (lower bound clears break-even)"
        elif high < be:
            verdict = "LOSES at this payout (upper bound is below break-even)"
        else:
            verdict = "UNPROVEN — the interval straddles break-even"
        print(f"  at {payout:.0%} payout    break-even {be:.1f}%  ->  {verdict}")

    print()
    for side, (w, n) in r["by_direction"].items():
        if n:
            print(f"  {side:<5} {w}/{n} = {w/n*100:.1f}%")

    if r["blocked"]:
        print("\n  what declined the rest:")
        for reason, count in sorted(r["blocked"].items(), key=lambda kv: -kv[1])[:6]:
            print(f"    {count:>5}  {reason[:70]}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Backtest the 5-minute engine on stored candles")
    parser.add_argument("--symbol", default="DERIV_V75")
    parser.add_argument("--days", type=int, default=3)
    parser.add_argument("--threshold", type=int, default=CONFIG.minimum_score)
    parser.add_argument("--separation", type=int, default=CONFIG.minimum_directional_difference)
    parser.add_argument("--step", type=int, default=0, help="seconds between evaluations")
    parser.add_argument("--sweep", action="store_true", help="try a range of thresholds")
    args = parser.parse_args()

    profile = profile_for(args.symbol)
    step = args.step or profile.evaluation_seconds

    print(f"\n{args.symbol} — 5-minute engine, {args.days}d of stored history, "
          f"evaluating every {step}s\n")

    if not args.sweep:
        report(run(args.symbol, args.days, args.threshold, args.separation, step))
        print()
        return 0

    print(f"{'score':>6} {'sep':>4} {'signals':>8} {'per day':>8} "
          f"{'W':>5} {'L':>5} {'rate':>7} {'95% CI':>15}")
    print("-" * 64)
    for threshold in (50, 55, 60, 65, 70, 75, 78, 82):
        for separation in (10, 18, 25):
            r = run(args.symbol, args.days, threshold, separation, step)
            if r.get("error"):
                print(f"{threshold:>6} {separation:>4}   {r['error']}")
                continue
            decided = r["wins"] + r["losses"]
            if decided == 0:
                print(f"{threshold:>6} {separation:>4} {r['signals']:>8} "
                      f"{r['signals']/r['span_days']:>8.1f} {'—':>5} {'—':>5} {'—':>7}")
                continue
            rate = r["wins"] / decided * 100
            low, high = wilson(r["wins"], decided)
            print(f"{threshold:>6} {separation:>4} {r['signals']:>8} "
                  f"{r['signals']/r['span_days']:>8.1f} {r['wins']:>5} {r['losses']:>5} "
                  f"{rate:>6.1f}% {f'{low:.0f}–{high:.0f}%':>15}")

    print()
    print("Break-even is 55.6% at an 80% payout, 52.4% at 91%.")
    print("Read the LOWER bound of the interval, never the headline rate: a row")
    print("showing 60% on 12 trades whose interval reaches down to 32% has not")
    print("demonstrated anything, and picking the best-looking row from a sweep")
    print("is how a backtest gets tuned into a result that does not repeat.")
    print()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
