"""
Milestone 1 (spec Phase 54): prove the candles before trusting them.

    "If the prices materially disagree: STOP. Fix the feed before
     building the signal engine."

This is the only check that can catch a whole class of silent failure. If
our tick bucketing is off by one boundary, every indicator downstream is
computed on bars that never existed -- and everything still runs, still
scores, still stores. The engine would be confidently wrong with no error
anywhere. So we build M1 bars ourselves from raw ticks, ask Deriv for its
own M1 bars over the same window, and compare OHLC bar by bar.

Deriv is the arbiter here, not us: it generated the series, so where we
disagree, we are wrong.

    .venv\\Scripts\\python.exe verify_feed.py
    .venv\\Scripts\\python.exe verify_feed.py --symbol R_50 --bars 40
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime, timezone

from app.config import get_settings
from app.market_data.deriv_feed import DerivSyntheticFeed, ticks_to_candles
from app.otc.config import OTC_SYMBOLS, enabled_symbols

# Deriv quotes volatility indices to 2-4 decimals depending on the index.
# Compare at a tolerance below the smallest quoted increment so a genuine
# mismatch cannot hide inside floating-point noise.
TOLERANCE = 1e-6


def _fmt(value: float) -> str:
    return f"{value:.5f}"


async def main() -> int:
    parser = argparse.ArgumentParser(description="Verify tick-built candles against the broker's own")
    parser.add_argument("--symbol", default=None, help="Deriv API symbol, e.g. R_75")
    parser.add_argument("--bars", type=int, default=30, help="how many M1 bars to compare")
    args = parser.parse_args()

    settings = get_settings()
    app_id = getattr(settings, "deriv_app_id", None)
    if not app_id:
        print("DERIV_APP_ID is not set in .env — cannot reach the feed.")
        return 2

    if args.symbol:
        api_symbol = args.symbol
        label = args.symbol
    else:
        enabled = enabled_symbols()
        if not enabled:
            print("No instrument is enabled in app/otc/config.py.")
            return 2
        label = enabled[0]
        api_symbol = OTC_SYMBOLS[label].api_symbol

    feed = DerivSyntheticFeed(app_id)
    print(f"Verifying {label} ({api_symbol}) against {feed.name}\n")

    # --- 1. raw ticks, and our own bars built from them -------------------
    try:
        ticks = await feed.fetch_ticks(api_symbol, 5000)
    except Exception as exc:
        print(f"FAILED to fetch ticks: {exc}")
        return 1

    if not ticks:
        print("FAILED: the feed returned no ticks.")
        return 1

    span = (ticks[-1][0] - ticks[0][0]).total_seconds()
    rate = len(ticks) / (span / 60) if span > 0 else 0.0
    print(f"ticks           {len(ticks)} over {span/60:.1f} min  ->  {rate:.1f} ticks/min")
    print(f"tick window     {ticks[0][0]:%H:%M:%S} .. {ticks[-1][0]:%H:%M:%S} UTC")

    # A gap check the health module cannot do from a single reading: if the
    # feed silently dropped a stretch, the bars over that stretch are built
    # from nothing and their high/low are fiction.
    gaps = [
        (a[0], (b[0] - a[0]).total_seconds())
        for a, b in zip(ticks, ticks[1:])
        if (b[0] - a[0]).total_seconds() > 30
    ]
    if gaps:
        print(f"\nWARNING  {len(gaps)} gap(s) longer than 30s in the tick stream:")
        for at, seconds in gaps[:5]:
            print(f"         {at:%H:%M:%S} -> {seconds:.0f}s")

    ours = ticks_to_candles(ticks, 60)
    if not ours:
        print("FAILED: no closed M1 bars could be built from those ticks.")
        return 1

    # --- 2. the broker's own bars over the same window --------------------
    try:
        theirs = await feed.fetch_bars(api_symbol, "M1", 200)
    except Exception as exc:
        print(f"FAILED to fetch broker bars: {exc}")
        return 1

    theirs_by_time = {b.open_time: b for b in theirs}
    ours_by_time = {c["open_time"]: c for c in ours}
    shared = sorted(set(theirs_by_time) & set(ours_by_time))[-args.bars:]

    if not shared:
        print("FAILED: our bars and the broker's share no timestamps.")
        print("        This is the boundary-alignment bug the check exists to catch.")
        print(f"        ours   {sorted(ours_by_time)[-3:]}")
        print(f"        theirs {sorted(theirs_by_time)[-3:]}")
        return 1

    print(f"\ncomparing {len(shared)} M1 bars\n")

    mismatches: list[str] = []
    for open_time in shared:
        a = ours_by_time[open_time]
        b = theirs_by_time[open_time]
        for field in ("open", "high", "low", "close"):
            mine, theirs_v = float(a[field]), float(getattr(b, field))
            if abs(mine - theirs_v) > TOLERANCE:
                mismatches.append(
                    f"  {open_time:%H:%M:%S}  {field:<6} ours {_fmt(mine)}  broker {_fmt(theirs_v)}"
                    f"  diff {mine - theirs_v:+.6f}"
                )

    # --- 3. verdict --------------------------------------------------------
    print("=" * 62)
    if mismatches:
        print(f"MISMATCH — {len(mismatches)} field(s) across {len(shared)} bars\n")
        for line in mismatches[:20]:
            print(line)
        if len(mismatches) > 20:
            print(f"  ... and {len(mismatches) - 20} more")
        print("\nSTOP. Per Phase 54, fix the feed before running any strategy on it.")
        print("Most likely causes, in order:")
        print("  1. tick buckets not aligned to absolute epoch boundaries")
        print("  2. the forming (unclosed) bar being included")
        print("  3. tick history too sparse to reconstruct the bar's high/low")
        return 1

    print(f"MATCH — {len(shared)} bars agree to {TOLERANCE:g} on all four OHLC fields.")
    print("\nThe candle engine reconstructs the broker's own series exactly.")
    print("Milestone 1 passes; the signal engine may be run on this feed.")

    if rate < 10:
        print(f"\nNOTE: {rate:.1f} ticks/min is below the health floor of 10.")
        print("      Sub-minute bars will be thin. Consider the 1s index variant.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except KeyboardInterrupt:
        sys.exit(130)
