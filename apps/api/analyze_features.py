"""
Does ANY feature predict which way price moves next?

WHY THIS AND NOT MORE TUNING
----------------------------
The sweep showed the technical score is flat: setups scoring 55 and 74 won
at the same rate across 1,575 resolved trades. That rules out a whole class
of fixes at once -- thresholds, meta-models, tighter regime gates all assume
the score ranks quality, and it measurably does not.

But "the combination is flat" does not mean "every input is noise". The
engine collapses RSI, EMA structure, MACD, ATR and swing structure into one
vote count. A vote count can be worthless while one of its inputs is not.

This asks each feature separately, against a clean label.

THE LABEL, AND WHY IT IS NOT THE ENGINE'S OUTCOME
-------------------------------------------------
For every decision point the label is simply: did price close HIGHER
`horizon` minutes later? That is deliberately independent of the engine's
direction rule. Testing features against the engine's own wins would only
tell you which features agree with a strategy already known not to work.

A feature that predicts "price rises" better than chance has value whatever
strategy eventually uses it.

NO LOOK-AHEAD
-------------
Features are computed from `replay.slice_history`, the same primitive the
backtester uses -- only bars closed at that moment are visible. The label
reads the future, which is the point, and never touches the features.

READING THE OUTPUT, AND THE TRAP IN IT
---------------------------------------
Each feature is split into five buckets by its own value, and the "up rate"
is shown per bucket. A feature with signal shows a MONOTONIC spread -- up
rate rising or falling steadily across buckets. A feature that is noise
shows five numbers scattered around 50%.

With ~15 features x 5 buckets, roughly one apparent winner WILL appear by
chance alone. So the summary ranks by spread and says plainly that any hit
needs confirming on data it was not found in. Finding a pattern here is a
hypothesis, not a result.

    .venv\\Scripts\\python.exe analyze_features.py
    .venv\\Scripts\\python.exe analyze_features.py --horizon 60 --step 30
"""
from __future__ import annotations

import argparse
import math
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from app.backtesting import replay
from app.backtesting.repository import load_history
from app.features import indicators as ind
from app.features import structure as struct
from app.schemas.candle import Asset

BUCKETS = 5
MIN_PER_BUCKET = 30


def wilson(wins: int, total: int) -> tuple[float, float]:
    if total == 0:
        return (0.0, 0.0)
    z, p, n = 1.96, wins / total, total
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    m = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, (c - m) * 100), min(100.0, (c + m) * 100))


def features_at(sliced: dict[str, list[dict]], now: datetime) -> dict[str, float]:
    """Everything the engine can see at this instant, as separate numbers
    rather than collapsed into one vote."""
    out: dict[str, float] = {}

    for tf in ("M5", "M15", "H1"):
        candles = sliced.get(tf, [])
        if len(candles) < 60:
            continue
        closes = [float(c["close"]) for c in candles]
        price = closes[-1]

        rsi = ind.rsi_latest(closes, 14)
        if rsi is not None:
            out[f"{tf}_rsi"] = rsi

        slope = ind.ema_slope(closes, 20)
        if slope is not None:
            out[f"{tf}_ema20_slope"] = slope

        ema20, ema50 = ind.ema_latest(closes, 20), ind.ema_latest(closes, 50)
        if ema20 and ema50:
            # Normalised so gold and EURUSD are comparable.
            out[f"{tf}_ema_gap_pct"] = (ema20 - ema50) / ema50 * 100
            out[f"{tf}_price_vs_ema20_pct"] = (price - ema20) / ema20 * 100

        macd = ind.macd_latest(closes)
        if macd is not None and price:
            out[f"{tf}_macd_hist_pct"] = macd.histogram / price * 100

        boll = ind.bollinger_latest(closes, 20)
        if boll is not None and boll.upper > boll.lower:
            # 0 = at the lower band, 100 = at the upper band.
            out[f"{tf}_boll_position"] = (price - boll.lower) / (boll.upper - boll.lower) * 100
            out[f"{tf}_boll_width_pct"] = boll.width_pct

        atr_pct = ind.atr_percentile(candles, 14)
        if atr_pct is not None:
            out[f"{tf}_atr_percentile"] = atr_pct

        last = candles[-1]
        high, low = float(last["high"]), float(last["low"])
        if high > low:
            out[f"{tf}_candle_close_position"] = (price - low) / (high - low) * 100

    out["hour_utc"] = float(now.hour)
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=14)
    parser.add_argument("--step", type=int, default=30, help="minutes between samples")
    parser.add_argument("--horizon", type=int, default=30, help="minutes ahead for the label")
    args = parser.parse_args()

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=args.days)

    print(f"\nSampling every {args.step} min over {args.days} days.")
    print(f"Label: did price close HIGHER {args.horizon} minutes later?")
    print("Features see only closed bars; the label sees the future. That is the point.\n")

    # feature -> list of (value, went_up)
    observations: dict[str, list[tuple[float, bool]]] = defaultdict(list)
    total = 0

    for asset in Asset:
        history = load_history(asset, start, end)
        m5 = history.get("M5", [])
        if not m5:
            continue

        by_time = {c["open_time"]: c for c in m5}
        points = [
            c["open_time"] for c in m5
            if start <= c["open_time"] <= end
            and int(c["open_time"].timestamp()) % (args.step * 60) == 0
        ]

        used = 0
        for as_of in points:
            future = by_time.get(as_of + timedelta(minutes=args.horizon))
            if future is None:
                continue
            here = by_time.get(as_of)
            if here is None:
                continue

            went_up = float(future["close"]) > float(here["close"])
            sliced = replay.slice_history(history, as_of)
            for name, value in features_at(sliced, as_of).items():
                observations[name].append((value, went_up))
            used += 1

        total += used
        print(f"  {asset.value:<8} {used:>5} samples")

    if total == 0:
        print("\nNo samples. Is history backfilled? Run backfill.py --run.\n")
        return

    print(f"\n{total} samples, {len(observations)} features.\n")

    results = []
    for name, rows in sorted(observations.items()):
        if len(rows) < BUCKETS * MIN_PER_BUCKET:
            continue
        rows.sort(key=lambda r: r[0])
        size = len(rows) // BUCKETS
        buckets = []
        for i in range(BUCKETS):
            chunk = rows[i * size:(i + 1) * size] if i < BUCKETS - 1 else rows[i * size:]
            ups = sum(1 for _, up in chunk if up)
            rate = 100 * ups / len(chunk)
            lo, hi = wilson(ups, len(chunk))
            buckets.append((chunk[0][0], chunk[-1][0], len(chunk), rate, lo, hi))

        rates = [b[3] for b in buckets]
        spread = max(rates) - min(rates)
        # A real relationship is monotonic, not one odd bucket in the middle.
        monotonic = (all(rates[i] <= rates[i + 1] for i in range(len(rates) - 1))
                     or all(rates[i] >= rates[i + 1] for i in range(len(rates) - 1)))
        results.append((spread, monotonic, name, buckets))

    results.sort(reverse=True, key=lambda r: r[0])

    for spread, monotonic, name, buckets in results:
        flag = "  <-- monotonic" if monotonic and spread > 4 else ""
        print(f"{name}   spread {spread:.1f} pts{flag}")
        for lo_v, hi_v, n, rate, lo, hi in buckets:
            bar = "#" * round(rate / 3)
            print(f"    {lo_v:>9.3f}..{hi_v:<9.3f} n={n:<5} up {rate:5.1f}%  "
                  f"[{lo:4.1f}-{hi:4.1f}]  {bar}")
        print()

    print("=" * 78)
    print("HOW TO READ THIS")
    print("=" * 78)
    print("A feature with real signal shows a MONOTONIC spread — the up rate rising")
    print("or falling steadily across buckets — with intervals that do not all overlap.")
    print("Noise shows five numbers scattered around 50%.")
    print()
    print(f"With {len(results)} features x {BUCKETS} buckets, roughly one apparent winner")
    print("WILL appear by chance. Anything found here is a hypothesis, not a result:")
    print("confirm it on a date range it was not found in before believing it.")
    print()
    print("If nothing is monotonic with a spread above ~4 points, that is the answer:")
    print("these features do not predict short-horizon direction, and no amount of")
    print("recombining them will change that.")


if __name__ == "__main__":
    main()
