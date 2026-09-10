"""
Fetch M1 history so the 5-minute engine can be BACKTESTED today.

WHY THIS EXISTS SEPARATELY FROM backfill.py
-------------------------------------------
backfill.py fetches M5 and derives M15/H1/H4 from it. That serves the
older multi-hour engine perfectly and cannot serve this one at all: the
5-minute engine's entry and confirmation timeframe is M1 and its momentum
timeframe is M3, and NEITHER can be built from M5 -- a three-minute bar is
not a whole number of five-minute bars, and a one-minute bar certainly is
not.

So the only M1 history in the database is whatever the live collector's
900-bar window happened to store. 900 minutes is fifteen hours, and the
engine's own warm-up is sixty M15 bars -- also fifteen hours. The window
left over to measure is zero, which is exactly what the backtest reported:

    not enough history for the warm-up window

Waiting fixes it eventually. This fixes it in three requests.

WHAT IT STORES
--------------
M1 as fetched, and M3/M5/M15 aggregated from it by the same
`aggregate_candles` the live collector uses -- one source, one aggregation
path. Deriving them from a separately fetched M5 series would put two
differently-bucketed versions of the same hour in one table, and the
backtest would then disagree with live for reasons nothing could explain.

Every row is written with feed_kind PUBLIC_MARKET. These are real market
bars and must never be readable as broker-OTC ones.

CREDIT COST
-----------
Twelve Data returns up to 5000 bars per request, so one page is about
3.5 days of one-minute bars. The default target is seven days -- two or
three pages for one symbol, against a 800/day free tier. It prints the
plan and spends nothing without --run.

    .venv\\Scripts\\python.exe backfill_m1.py            (preview)
    .venv\\Scripts\\python.exe backfill_m1.py --run      (fetch and store)
    .venv\\Scripts\\python.exe backfill_m1.py --run --days 14
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime, timedelta, timezone

from app.aggregation import Candle as AggCandle
from app.aggregation import Timeframe as AggTimeframe
from app.aggregation import aggregate_candles
from app.collector.scheduler import build_provider
from app.config import get_settings
from app.market_data.closed_bars import split_closed
from app.otc.config import enabled_market_symbols
from app.schemas.candle import Asset

PAGE_SIZE = 5_000
MINUTES_PER_DAY = 1_440

# Derived from M1, never fetched -- the same tuple the live collector uses.
DERIVED: tuple[tuple[str, AggTimeframe], ...] = (
    ("M3", AggTimeframe.M3),
    ("M5", AggTimeframe.M5),
    ("M15", AggTimeframe.M15),
)


def _as_dict(candle) -> dict:
    return {
        "open_time": candle.open_time,
        "open": float(candle.open),
        "high": float(candle.high),
        "low": float(candle.low),
        "close": float(candle.close),
    }


async def backfill_symbol(symbol: str, provider, days: int, *, store: bool) -> int:
    from app.storage.candle_repository import upsert_otc_candles

    try:
        asset = Asset(symbol)
    except ValueError:
        print(f"  {symbol}: not a public-market instrument — skipped")
        return 0

    target = days * MINUTES_PER_DAY
    collected: dict[datetime, object] = {}
    now = datetime.now(timezone.utc)
    cursor = now
    page = 0

    while len(collected) < target:
        page += 1
        try:
            bars = await provider.fetch_m1_before(asset, cursor, PAGE_SIZE)
        except Exception as exc:  # noqa: BLE001
            print(f"    page {page}: FAILED — {exc}")
            break

        if not bars:
            print(f"    page {page}: no history before {cursor:%Y-%m-%d %H:%M}")
            break

        # The same closed-bar rule as live ingestion. A bar still forming is
        # more corrupting in history than in real time, because the backtest
        # will replay it as though it had closed.
        closed = list(split_closed(bars, "M1", now).closed)
        fresh = [b for b in closed if b.open_time not in collected]
        for bar in closed:
            collected[bar.open_time] = bar

        oldest = min(b.open_time for b in closed) if closed else cursor
        print(f"    page {page}: +{len(fresh):>5} new  (total {len(collected):>6})  "
              f"back to {oldest:%Y-%m-%d %H:%M}")

        if not fresh:
            print("    no new bars in this page — history exhausted")
            break
        # A short page means the provider has nothing older. Asking again
        # spends a request to be told the same thing.
        if len(bars) < PAGE_SIZE:
            print(f"    short page ({len(bars)}) — provider history ends here")
            break

        cursor = oldest - timedelta(minutes=1)

    if not collected or not store:
        return len(collected)

    ordered = sorted(collected.values(), key=lambda c: c.open_time)
    rows = [_as_dict(c) for c in ordered]
    upsert_otc_candles(
        symbol, "M1", rows,
        source=f"{provider.name}+backfill", feed_kind="PUBLIC_MARKET",
    )
    print(f"    OK  M1   {len(rows):>6} bars stored")

    source = [
        AggCandle(open_time=c.open_time, open=c.open, high=c.high, low=c.low, close=c.close)
        for c in ordered
    ]
    for name, target_tf in DERIVED:
        derived = aggregate_candles(source, AggTimeframe.M1, target_tf, now=now)
        if not derived:
            print(f"    ... {name:<4} nothing derived")
            continue
        upsert_otc_candles(
            symbol, name, [_as_dict(c) for c in derived],
            source=f"{provider.name}+backfill+aggregated", feed_kind="PUBLIC_MARKET",
        )
        print(f"    OK  {name:<4} {len(derived):>6} bars stored")

    return len(rows)


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", action="append", default=None,
                        help="repeatable; defaults to the enabled market symbols")
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--run", action="store_true",
                        help="actually fetch and store; without it nothing is spent")
    args = parser.parse_args()

    settings = get_settings()
    if not settings.has_real_provider:
        print("TWELVE_DATA_API_KEY is not set. Backfill needs the real provider —")
        print("demo candles are placeholders and would poison the history.")
        sys.exit(1)
    if args.run and not settings.has_supabase:
        print("SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY must be set to store anything.")
        sys.exit(1)

    symbols = args.symbol or enabled_market_symbols()
    if not symbols:
        print("No market symbols are enabled in app/otc/config.py.")
        sys.exit(1)

    pages = -(-args.days * MINUTES_PER_DAY // PAGE_SIZE)
    print(f"\nM1 backfill plan: {', '.join(symbols)} — up to {pages} page(s) each "
          f"= up to {len(symbols) * pages} API requests")
    print(f"Target: {args.days} days of M1, with M3/M5/M15 aggregated from it.")
    print("Twelve Data free tier is 800 requests/day.\n")

    if not args.run:
        print("PREVIEW ONLY — nothing fetched, nothing stored, no credits spent.")
        print("Re-run with --run to execute.\n")
        return

    provider = build_provider()
    total = 0
    for symbol in symbols:
        print(f"  {symbol}")
        total += await backfill_symbol(symbol, provider, args.days, store=True)

    print(f"\nDone. {total:,} M1 bars stored.")
    print("Now run otc-backtest.bat --sweep; there is finally something to replay.")


if __name__ == "__main__":
    asyncio.run(main())
