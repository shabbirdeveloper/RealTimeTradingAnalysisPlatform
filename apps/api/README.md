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

One request per asset per cycle — only M5 is fetched; M15/H1/H4 are
derived locally, which is roughly a 4x saving.

There are now **5 assets on two different schedules**: forex/gold
(XAUUSD, EURUSD, GBPUSD) trade ~17.3 h/day averaged over the week, while
crypto (BTCUSD, ETHUSD) trades 24/7. Polling is skipped per-asset when
that asset's market is closed (`app/collector/market_hours.py`), so the
budget is:

| `POLL_INTERVAL_SECONDS` | approx. requests/day | vs 800 free |
|---|---:|---|
| 300 | ~1,198 | **over** |
| 450 | ~799 | at the limit |
| **600 (default)** | **~599** | comfortable |
| 900 | ~399 | very conservative |

The default was raised from 300s to 600s when crypto was added — at 300s
five assets blow through the free tier before the day is out, and the
collector would simply start failing. Lower it only if your plan allows
more requests.

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

## Day-to-day (Windows)

Double-click these in `apps/api`, or run them from any prompt on any drive:

| File | What it does |
| --- | --- |
| `install-autostart.bat` | **Run once.** Starts the collector at every logon, and restarts it if it crashes. No admin rights. |
| `start-collector.bat` | Starts it in the foreground. Closing the window stops collection. |
| `run-collector-forever.bat` | Same, but restarts after a crash. This is what autostart runs. |
| `check.bat` | Reports where the pipeline is stuck. Safe any time. |
| `backfill.bat --run` | Fetches historical candles so the engine can warm up. |

The collector must run continuously — it accumulates candle history and
resolves signals when they reach expiry. Every gap is history never collected
and signals never scored, and both are unrecoverable after the fact.

`install-autostart.bat` fixes the two ways it has actually died: the terminal
window being closed, and the machine restarting. It installs into the per-user
Startup folder rather than creating a scheduled task — `schtasks /sc onlogon`
requires administrator rights and fails with "Access is denied" on a normal
account. `uninstall-autostart.bat` reverses it. It does **not** fix sleep. A
laptop that sleeps still stops collecting; genuinely continuous operation
needs a machine that stays awake.

### Logs

The collector writes to `apps/api/logs/collector.log` (5 files, 2MB each).
Console output dies with the window, which is why the first two crashes left
no evidence. Query parameters named `apikey`, `token`, `password` and similar
are redacted before anything reaches disk — the Twelve Data key travels in a
URL, and a log file is a durable artifact that gets attached to bug reports.

Each begins with `cd /d "%~dp0"` for a specific reason: plain `cd` on Windows
changes the directory on a drive without switching to it, so `cd F:\...` typed
at a `C:` prompt leaves you on `C:` and every relative path silently resolves
in the wrong place.

## Warming up the engine (backfill)

The engine needs 250 bars per timeframe before it will analyse one. The live
collector adds ~12 M5 bars an hour, so H4 would take about 41 days to reach
that on its own. This fetches the history in one pass:

```bash
.venv\Scripts\python.exe backfill.py          # preview — spends no credits
.venv\Scripts\python.exe backfill.py --run    # fetch and store
```

Only M5 is fetched; M15/H1/H4 are derived from it by the same aggregation the
live collector uses. Requesting each timeframe from the provider directly
would be four times cheaper and would mix two differently-built series in one
table — a provider's H4 uses its own bucket conventions, which need not match
ours, and the mismatch would surface later as a backtest that quietly
disagrees with live.

## Getting told when a signal fires

The engine rejects most cycles by design, so signals are rare — and a rare
signal you don't see is worth nothing. Set `TELEGRAM_BOT_TOKEN` and
`TELEGRAM_CHAT_ID` in `.env` (see `.env.example` for how to get both) and new
CALL/PUT signals arrive on your phone.

Only **newly created** directional signals alert. A setup that stands for an
hour is one opportunity, not six, and NO_TRADE cycles never alert at all — a
channel that pings constantly is one you stop reading, and then the message
that mattered goes unread too.

Unset means signals are still recorded and visible in the dashboard, just not
pushed anywhere.

## "Why is it always NO TRADE?"

```bash
sweep.bat                    # replay 14 days, decision every 15 minutes
sweep.bat --days 7 --step 5  # shorter window, finer grain
```

Replays real stored history with no look-ahead and reports, for each candidate
threshold, how many setups it would have taken and what share of them won —
with a 95% confidence interval on each win rate.

Watching the live dashboard cannot distinguish "the market offers nothing right
now" from "these rules would reject almost anything", because both show the
same NO TRADE card. Replaying weeks of stored history can, in minutes.

Read it by the LOWER interval bound against break-even (55.6% at an 80%
payout), never by the win rate alone. A 75% win rate on 8 trades has a 95%
interval of 41–93%, which is not evidence of anything.

## Checking whether signals are working

```bash
.venv\Scripts\python.exe diagnose.py      # Windows
.venv/bin/python diagnose.py               # macOS / Linux
```

Walks the pipeline in order — config, database, migrations, candles, warm-up,
decisions, failures, resolution — and stops at the FIRST broken stage, because
a later stage failing is usually an echo of an earlier one. Read-only; it never
prints a credential.

The distinction it exists to draw: "no signals" has several completely
different causes that look identical from the dashboard.

| What you see | What it actually means |
| --- | --- |
| No candles | The collector isn't running |
| Candles, all stale | It stopped, or its polls are failing |
| Fewer than 250 bars | Warming up — NO_TRADE is correct here |
| Missing schema column | Migrations not applied; every signal write throws |
| Decisions, all NO_TRADE | Working. It is rejecting setups, which is the point |

## Running the tests

`app/aggregation.py`, everything under `app/features/` (indicators,
structure, regime, timeframe bias, the signal engine), and the
backtester's replay/engine core under `app/backtesting/` are
unit-tested — all zero-dependency, pure Python, so they run anywhere
Python 3.10+ runs, no `pip install` required:

```bash
python -m unittest discover -s tests -t . -v
```

(115/115 passing as of when this was written.) The storage layer, the
provider, and the scheduler depend on `fastapi`/`httpx`/`supabase`/
`apscheduler`, which are exercised by actually running the service (see
"Verified this session" in `docs/PHASE-STATUS.md`) rather than by unit
tests — the feature/signal engine writes were added after that last live
verification and have **not yet been run against the real Supabase
project**; that's the next thing to do after restarting this service.

## What's NOT done yet

- Not deployed anywhere (Dockerfile exists for later; nothing runs this
  in AWS/VPS/Docker today, only locally via `uvicorn`).
- No retry/backoff on transient provider errors — a failed poll just logs
  a warning and tries again next cycle.
- No WebSocket server in this service. Real-time delivery to the frontend
  is expected to go through **Supabase Realtime** (Postgres change feed
  on `candles`), not a custom WebSocket layer here — simpler, and the
  spec explicitly allows "Supabase Realtime where appropriate."
- `market_hours.is_market_open()` is a blunt weekend check — separate
  from the real session detection now in `app/features/structure.py`
  (`session_for_time`, Asian/London ranges), which is used for analysis,
  not for deciding whether to poll at all.
- Feature calculation, regime detection, multi-timeframe bias, and a
  rule-based signal engine (Phases 3-4) are now real — see
  `app/features/` and `docs/PHASE-STATUS.md`'s "Real signal engine"
  section for exactly what's real and what's explicitly not (no
  calibrated ML confidence, no meta model, no news filter, thin early
  history).
- Signal resolution (spec section 49) and the historical backtester
  (spec section 13) are both real now — see `app/collector/resolution.py`
  and `app/backtesting/`. The backtester's no-look-ahead guarantee lives
  in `app/backtesting/replay.py` and is covered by a regression test that
  corrupts all future candles and asserts an earlier decision is
  unchanged.
- **This service has no user auth.** It holds the Supabase service-role
  key and assumes a private network. The admin endpoints
  (`POST /admin/backtests`, `GET /admin/backtests/{id}`) check a shared
  secret in the `X-Admin-Api-Key` header against `ADMIN_API_KEY` and fail
  closed when it is unset. That is a minimum bar, not real auth — put a
  proper auth layer in front of this service before exposing it publicly,
  and remove or gate `/debug/poll-now` as noted above.
- Backtest results are only as meaningful as the candle history stored so
  far. A run over a few days is a smoke test of the rules, not evidence
  of accuracy (spec section 15).
- **Broker-synthetic / "OTC" instruments are refused, not supported.**
  `app/instruments.py` rejects any symbol that looks like a broker OTC or
  synthetic instrument before it can reach the analysis path. Those
  weekend instruments are price series generated by the broker, not real
  markets — this platform analyses real market data, so a signal about
  them would be unrelated to what actually settles, while still rendering
  as a confident graded result. The project also forbids sourcing
  broker-side prices, so there is no honest way to analyse them. For
  genuine weekend coverage use the 24/7 crypto assets instead.

- **No economic calendar provider is connected.** The news-blackout
  policy (`app/news/blackout.py`) is built and tested — pre-news pause,
  NEWS_MODE, post-event stabilization, configurable windows, asset↔
  currency relevance — and wired into the signal engine. What's missing
  is a data feed. Until one is configured, `NullCalendarProvider` reports
  `is_configured = False` and every signal carries a loud warning that
  news is NOT being screened; an empty calendar is never treated as an
  all-clear.

  To connect one: subclass `EconomicCalendarProvider` in
  `app/news/base.py`, implement `fetch_upcoming()` returning tz-aware UTC
  `ProviderEvent`s, and select it in `app/news/factory.py`. Storage
  (`app/storage/event_repository.py`), the blackout policy, the engine
  wiring, and the calendar UI are all already done.
