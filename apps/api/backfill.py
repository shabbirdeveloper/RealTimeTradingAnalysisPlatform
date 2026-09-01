"""
Fill historical candle history so the engine can warm up in minutes rather
than weeks.

WHY THIS IS NEEDED
------------------
The live collector adds roughly 12 M5 bars per hour. The engine needs 250
bars per timeframe before it will analyse one, and higher timeframes are
built from M5, so the wait compounds badly:

    M5    250 bars  ~13 hours of running
    M15   250 bars  ~2 days
    H1    250 bars  ~10 days
    H4    250 bars  ~41 days

Forty-one days before the engine reaches full strength is not a warm-up, it
is a blocker. This fetches the history in one pass instead.

HOW IT PRESERVES THE SINGLE-SOURCE RULE
---------------------------------------
Only M5 is fetched. M15/H1/H4 are derived from it by the same
`aggregate_candles` the live collector uses.

The tempting shortcut is to request each timeframe directly from the
provider -- four times fewer requests. That would mix two differently-built
series in one table: a provider's H4 uses its own session and bucket
conventions, which need not match ours. The mismatch would be invisible in
the data and would surface as a backtest that quietly disagrees with live.
One source, one aggregation path, whatever it costs in requests.

CREDIT COST
-----------
Twelve Data returns up to 5000 bars per request. 250 H4 bars needs 250 x 48
= 12,000 M5 bars, so three pages per asset -- about 15 requests for five
assets, against a 800/day free tier. It prints the estimate and asks before
spending anything.

    .venv\\Scripts\\python.exe backfill.py            (preview, spends nothing)
    .venv\\Scripts\\python.exe backfill.py --run      (actually fetch)
"""
from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timedelta, timezone

from app.aggregation import Candle as AggCandle
from app.aggregation import Timeframe as AggTimeframe
from app.aggregation import aggregate_candles
from app.collector.scheduler import build_provider
from app.config import get_settings
from app.market_data.closed_bars import split_closed
from app.schemas.candle import Asset, Candle, Timeframe

# 250 closed H4 bars need 250 x 48 M5 bars. The extra page covers weekend
# gaps in forex, where wall-clock time does not map one-to-one onto bars.
TARGET_M5_BARS = 15_000
PAGE_SIZE = 5_000
WARMUP_BARS = 250


def to_agg(c: Candle) -> AggCandle:
    return AggCandle(open_time=c.open_time, open=c.open, high=c.high, low=c.low,
                     close=c.close, volume=c.volume)


def from_agg(c: AggCandle) -> Candle:
    return Candle(open_time=c.open_time, open=c.open, high=c.high, low=c.low,
                  close=c.close, volume=c.volume)


async def backfill_asset(asset: Asset, provider, *, store) -> int:
    """Pages backwards until TARGET_M5_BARS is reached or history runs out."""
    from app.storage.candle_repository import upsert_candles

    collected: dict[datetime, Candle] = {}
    cursor = datetime.now(timezone.utc)
    now = cursor

    for page in range(1, (TARGET_M5_BARS // PAGE_SIZE) + 2):
        if len(collected) >= TARGET_M5_BARS:
            break
        try:
            bars = await provider.fetch_m5_before(asset, cursor, PAGE_SIZE)
        except Exception as exc:  # noqa: BLE001
            print(f"    page {page}: FAILED — {exc}")
            break

        if not bars:
            print(f"    page {page}: provider has no history before {cursor:%Y-%m-%d %H:%M}")
            break

        # Same closed-bar rule as live ingestion. A partial bar is just as
        # corrupting in history as it is in real time -- more so, because the
        # backtester will replay it.
        split = split_closed(bars, Timeframe.M5.value, now)
        fresh = [b for b in split.closed if b.open_time not in collected]
        for bar in split.closed:
            collected[bar.open_time] = bar

        oldest = min(b.open_time for b in split.closed) if split.closed else cursor
        print(f"    page {page}: +{len(fresh):>5} new  (total {len(collected):>6})  "
              f"back to {oldest:%Y-%m-%d %H:%M}")

        if not fresh:
            print("    no new bars in this page — history exhausted")
            break
        cursor = oldest - timedelta(minutes=5)

    if not collected:
        return 0

    ordered = sorted(collected.values(), key=lambda c: c.open_time)
    if store:
        upsert_candles(asset, Timeframe.M5, ordered, source=f"{provider.name}+backfill")

        agg_source = [to_agg(c) for c in ordered]
        for target, agg_target in (
            (Timeframe.M15, AggTimeframe.M15),
            (Timeframe.H1, AggTimeframe.H1),
            (Timeframe.H4, AggTimeframe.H4),
        ):
            derived = aggregate_candles(agg_source, AggTimeframe.M5, agg_target, now=now)
            if derived:
                upsert_candles(
                    asset, target, [from_agg(c) for c in derived],
                    source=f"{provider.name}+backfill+aggregated",
                )
            marker = "OK " if len(derived) >= WARMUP_BARS else "..."
            print(f"    {marker} {target.value:<4} {len(derived):>5} bars derived")
    return len(ordered)


async def main() -> None:
    store = "--run" in sys.argv
    settings = get_settings()

    if not settings.has_real_provider:
        print("TWELVE_DATA_API_KEY is not set. Backfill needs the real provider —")
        print("demo candles are placeholders and would poison the history.")
        sys.exit(1)
    if store and not settings.has_supabase:
        print("SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY must be set to store anything.")
        sys.exit(1)

    provider = build_provider()
    assets = list(Asset)
    pages = (TARGET_M5_BARS // PAGE_SIZE) + 1
    print(f"\nBackfill plan: {len(assets)} assets x up to {pages} pages "
          f"= up to {len(assets) * pages} API requests")
    print(f"Target: {TARGET_M5_BARS:,} M5 bars each, enough to derive {WARMUP_BARS}+ H4 bars.")
    print("Twelve Data free tier is 800 requests/day; the live collector uses ~600.\n")

    if not store:
        print("PREVIEW ONLY — nothing fetched, nothing stored, no credits spent.")
        print("Re-run with --run to execute.\n")
        return

    total = 0
    for asset in assets:
        print(f"  {asset.value}")
        total += await backfill_asset(asset, provider, store=True)

    print(f"\nDone. {total:,} M5 bars stored across {len(assets)} assets.")
    print("Run diagnose.py to confirm the warm-up state, then restart the API.")


if __name__ == "__main__":
    asyncio.run(main())
