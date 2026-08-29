# apps/api — market data collector service

Phase 2 of the project spec: a small Python/FastAPI service that pulls
real OHLC candles for XAU/USD, EUR/USD, GBP/USD, stores them in Supabase,
and derives the higher timeframes the rest of the app needs. Nothing in
this service places trades or talks to Quotex — it only reads market data
and writes to the database (spec section 43).

## What this does, concretely

1. Every `POLL_INTERVAL_SECONDS`, for each of the 3 assets: fetch the
   latest M5 candles from the configured provider (Twelve Data by
   default).
2. Upsert those M5 candles into the `candles` table.
3. Derive M15 / H1 / H4 candles from stored M5 history — **not** fetched
   separately from the provider — and upsert those too. This is why the
   provider interface (`app/market_data/base.py`) only has one method:
   `fetch_latest_m5`.
4. Write a row per asset into `system_health` (`component =
   "market_data.XAUUSD"` etc.) so `/admin/market-data` can eventually read
   real status instead of demo data.

## Why M15/H1/H4 are derived, not fetched

Twelve Data's free tier is 800 requests/day, 8 credits/minute. Fetching
all 4 timeframes for all 3 assets on a tight interval blows through that
almost immediately. Fetching only M5 (the finest granularity) and
aggregating the rest locally cuts API usage to roughly 1/4, and the
aggregation logic (`app/aggregation.py`) is a pure, dependency-free
function with its own unit tests (`tests/test_aggregation.py`) — verified
correct (bucket alignment, no look-ahead/no-partial-bar-as-closed,
gap handling) independently of the provider, the database, or the network.

### API credit budget (free tier: 800 req/day)

With `POLL_INTERVAL_SECONDS=300` (5 minutes) and 3 assets polled
back-to-back each cycle: `(1440 minutes/day ÷ 5) × 3 assets ≈ 864
requests/day` — slightly *over* the free tier's 800/day. Options:
- Set `POLL_INTERVAL_SECONDS=360` (6 minutes) → ~720/day, comfortably under.
- Only run the collector during the sessions you actually care about.
- Upgrade to a paid Twelve Data plan.

The collector also skips polling entirely on weekends
(`app/collector/market_hours.py`), which removes ~2 days/week worth of
otherwise-wasted requests when forex is closed anyway.

## Setup

```bash
cd apps/api
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
cp .env.example .env           # then fill in real values
```

Required in `.env` before the collector will actually write anything:
- `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` — from Supabase Dashboard →
  Settings → API. **Service role key, not anon** — this process bypasses
  RLS by design. Never put this key in `apps/web` or in Vercel.
- `TWELVE_DATA_API_KEY` — from twelvedata.com. **Leave it unset** to run
  against the built-in demo provider instead (synthetic, clearly
  arbitrary placeholder prices, zero cost, useful for exercising the
  pipeline before you have a real key).

Run it:

```bash
uvicorn app.main:app --reload
```

Then check `http://127.0.0.1:8000/health`.

## Running the tests

Only `app/aggregation.py` is unit-tested so far — it's the one piece with
zero third-party dependencies, so it runs anywhere Python 3.10+ runs, no
`pip install` required:

```bash
python -m unittest discover -s tests -t . -v
```

(Already run and passing as of when this was written — 12/12 tests.)
Everything else in this service (the provider, the storage layer, the
scheduler) depends on `fastapi`/`httpx`/`supabase`/`apscheduler`, which
were written but have **not** been executed anywhere yet — only checked
for valid Python syntax. First real run happens when you `pip install -r
requirements.txt` and start it yourself.

## What's NOT done yet

- Not deployed anywhere (Dockerfile exists for later; nothing runs this
  in AWS/VPS/Docker today, only locally via `uvicorn`).
- No retry/backoff on transient provider errors — a failed poll just logs
  a warning and tries again next cycle.
- No WebSocket server in this service. Real-time delivery to the frontend
  is expected to go through **Supabase Realtime** (Postgres change feed
  on `candles`), not a custom WebSocket layer here — simpler, and the
  spec explicitly allows "Supabase Realtime where appropriate."
- `market_hours.is_market_open()` is a blunt weekend check, not the real
  session-detection engine (spec section 6/7) — that belongs to a later
  phase's feature engine.
- Feature calculation (spec section 6), regime detection, and everything
  from Phase 3 onward are not part of this service yet.
