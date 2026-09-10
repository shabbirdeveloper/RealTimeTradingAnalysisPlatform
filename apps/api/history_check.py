"""
What is ACTUALLY stored, per timeframe — and what the backtest will see.

WHY THIS EXISTS
---------------
The backfill reported forty thousand M1 bars stored and the backtest, run
straight afterwards, measured the same 0.7-day window it had measured
before the backfill: identical evaluation count, identical span. One of
those two numbers is wrong, and neither report can say which, because
each one only sees its own half.

This reads the database directly and prints both halves side by side:
what the table holds, and what load() hands the replay. When they
disagree, the disagreement is the bug.

    .venv\\Scripts\\python.exe history_check.py
    .venv\\Scripts\\python.exe history_check.py --symbol XAUUSD --days 30
"""
from __future__ import annotations

import argparse
from datetime import timedelta

from app.otc.config import CONFIG, TIMEFRAME_SECONDS, profile_for
from app.storage.candle_repository import asset_id_for_symbol, fetch_recent_otc_candles
from app.storage.supabase_client import get_service_client


def stored_span(asset_id: str, timeframe: str) -> tuple[int, str, str]:
    client = get_service_client()
    total = (
        client.table("candles")
        .select("open_time", count="exact")
        .eq("asset_id", asset_id).eq("timeframe", timeframe)
        .limit(1).execute()
    ).count or 0

    def edge(desc: bool) -> str:
        rows = (
            client.table("candles").select("open_time")
            .eq("asset_id", asset_id).eq("timeframe", timeframe)
            .order("open_time", desc=desc).limit(1).execute()
        ).data or []
        return rows[0]["open_time"][:16].replace("T", " ") if rows else "—"

    return total, edge(False), edge(True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="XAUUSD")
    parser.add_argument("--days", type=int, default=3)
    args = parser.parse_args()

    profile = profile_for(args.symbol)
    asset_id = asset_id_for_symbol(args.symbol)
    print(f"\n{args.symbol} — asset_id {asset_id}")
    print(f"profile {profile.name}: required {', '.join(profile.required)}, "
          f"entry {profile.entry}\n")

    print("IN THE TABLE")
    print(f"  {'tf':<5}{'rows':>8}  {'oldest':<17}{'newest':<17}")
    for tf in profile.timeframes:
        total, oldest, newest = stored_span(asset_id, tf)
        print(f"  {tf:<5}{total:>8}  {oldest:<17}{newest:<17}")

    print(f"\nWHAT THE BACKTEST LOADS AT --days {args.days}")
    print(f"  {'tf':<5}{'asked':>8}{'got':>8}  {'covers':<12}{'warm at':<17}")
    ready = []
    for tf in profile.timeframes:
        seconds = TIMEFRAME_SECONDS[tf]
        needed = int(args.days * 86400 / seconds) + CONFIG.min_bars_per_timeframe + 60
        rows = fetch_recent_otc_candles(args.symbol, tf, min(needed, 5000))
        if not rows:
            print(f"  {tf:<5}{needed:>8}{0:>8}  nothing stored")
            continue
        span = (rows[-1]["open_time"] - rows[0]["open_time"]).total_seconds() / 86400
        warm = "—"
        if len(rows) >= CONFIG.min_bars_per_timeframe and tf in profile.required:
            at = rows[CONFIG.min_bars_per_timeframe - 1]["open_time"] + timedelta(seconds=seconds)
            ready.append((tf, at))
            warm = f"{at:%Y-%m-%d %H:%M}"
        print(f"  {tf:<5}{min(needed,5000):>8}{len(rows):>8}  {span:>5.1f} days  {warm:<17}")

    entry = fetch_recent_otc_candles(args.symbol, profile.entry, 5000)
    if ready and entry:
        tf, start = max(ready, key=lambda p: p[1])
        end = entry[-1]["open_time"]
        window = (end - start).total_seconds() / 86400
        print(f"\n  start   {start:%Y-%m-%d %H:%M}   (set by {tf}, the last to warm up)")
        print(f"  end     {end:%Y-%m-%d %H:%M}")
        print(f"  window  {window:.2f} days")
        if window <= 0:
            print("\n  Nothing to measure: warm-up ends after the history does.")
        else:
            print(f"\n  ~{int(window * 86400 / profile.evaluation_seconds)} evaluations "
                  f"at one every {profile.evaluation_seconds}s.")
    print()


if __name__ == "__main__":
    main()
