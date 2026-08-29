# Phase status

Tracking against the 10 phases defined in the project spec.

| Phase | Scope | Status |
|---|---|---|
| 1 | Project architecture, database, auth, dashboard, responsive nav, assets, mock UI | Frontend shell done. Database schema applied to a real Supabase project (confirmed — see below). Auth is wired for real and confirmed live: login/register/forgot-password/reset-password call actual `supabase.auth` methods, `apps/web/src/app/auth/callback/route.ts` handles email-link redirects, `middleware.ts` enforces server-side redirect protection on `/dashboard` and `/admin`. `/dashboard` (home) now reads real prices from Supabase — see "Dashboard home now reads real prices" below; every other dashboard/admin page (signals, markets, analyzer, history, performance, etc.) still runs on the frontend demo engine, honestly, since Phase 3/4 don't exist yet. |
| 2 | Real market-data abstraction, candle storage, WebSocket data flow, feature calculation | **Confirmed working end-to-end** — `apps/api/` (Python/FastAPI) fetches real M5 candles from Twelve Data, derives M15/H1/H4 in-process, writes both into `candles`, and reports per-asset status into `system_health`. Verified live: real rows visible in Supabase's `candles` and `system_health` tables (not just "should work"). Feature calculation (spec section 6) not started — that's Phase 3. See "Market data collector service" below. |
| 3 | Technical analysis, structure analysis, regime engine, multi-timeframe engine | Simulated in the frontend demo engine only (`apps/web/src/data/engine.ts`) — not a real implementation |
| 4 | Signal engine (CALL/PUT/NO TRADE, expiries, scoring, history) | Simulated in the frontend demo engine only |
| 5 | Backtesting engine, result calculation, analytics | Demo-only backtest builder in the frontend (`buildDemoBacktest`) — not connected to any real historical data or execution logic |
| 6 | ML pipeline, independent models, meta model, probability calibration | Not started. UI already distinguishes `MODEL_NOT_READY` from a calibrated confidence, per spec section 10 |
| 7 | News filter, economic calendar | Frontend UI + static demo calendar data only; no real economic-calendar API integration |
| 8 | Browser/Telegram notifications, PWA | Notification preferences UI built; manifest wired; service worker and real push delivery not implemented |
| 9 | Admin model tools, backtesting comparison, system monitoring | Frontend shells built with demo data; no real backend behind them |
| 10 | Subscription/billing architecture | Frontend billing UI only; no payment provider integration |

## Database schema (confirmed applied)

`supabase/migrations/` has 9 SQL files, run in order against the real
Supabase project and confirmed working (the `assets`/`candles`/
`system_health` tables are live and holding real rows):

1. `20260829000001_extensions_and_enums.sql` — pgcrypto + all enum types
2. `20260829000002_core_reference_tables.sql` — profiles, subscriptions, assets, economic_events (+ auto-create-profile-on-signup trigger)
3. `20260829000003_market_data_tables.sql` — candles, market_features (bigint identity PKs — highest-volume tables)
4. `20260829000004_ml_tables.sql` — models, model_versions (only one ACTIVE version per model, enforced by a partial unique index), model_predictions
5. `20260829000005_signals_tables.sql` — signals (spec section 37's exact columns), signal_results
6. `20260829000006_backtesting_tables.sql` — backtests, backtest_signals
7. `20260829000007_notifications_and_system_tables.sql` — notification_preferences (auto-created per user), notifications, system_health, audit_logs
8. `20260829000008_rls_policies.sql` — RLS on every table. Read-only for `authenticated` on market/signal/model data; strictly own-row for profile/subscription/notifications; admin-only (via an `is_admin()` security-definer helper, to avoid the classic self-referential-RLS recursion) for backtests/audit_logs/system_health and the CANDIDATE/REJECTED half of signals. All actual writes to those tables are expected to come from `apps/api` via the service-role key, which bypasses RLS — the policies here only cover what the browser is allowed to read/touch directly.
9. `20260829000009_seed_assets.sql` — seeds the 3 configured instruments (XAUUSD/EURUSD/GBPUSD) into `assets`. Added this session after the collector's first real run failed with "assets table is missing rows" — migrations 1-8 create the schema but were never going to seed data on their own; this was a genuine gap, not an optional extra.

## Market data collector service (`apps/api/`) — verified working

A Python/FastAPI service, independent of `apps/web`, whose only job is to
keep the `candles` table populated with real OHLC data:

- `app/market_data/` — provider abstraction (`base.py`) plus two
  implementations: `twelve_data_provider.py` (real REST calls to
  `api.twelvedata.com`, forces UTC timestamps) and `demo_provider.py`
  (deterministic, zero-network, clearly-arbitrary placeholder prices, for
  exercising the pipeline without an API key).
- `app/aggregation.py` — pure, dependency-free function that derives M15/
  H1/H4 candles from stored M5 history, so the provider is only ever
  asked for M5 (roughly 4x fewer API calls than fetching every
  timeframe). Never emits a bucket that might still be forming — see the
  module docstring for the exact closed-bucket rule. **Unit tested**:
  `tests/test_aggregation.py`, 12/12 passing.
- `app/storage/` — `candle_repository.py` (upserts into `candles`,
  dedupes on the same `(asset_id, timeframe, open_time)` unique
  constraint the migration defines) and `health_repository.py` (upserts
  per-component rows into `system_health`, e.g. `market_data.XAUUSD`).
- `app/collector/` — `service.py` (one poll cycle: fetch → store M5 →
  aggregate → store M15/H1/H4 → report health) and `scheduler.py`
  (APScheduler, runs `service.py` on an interval, skips weekends).
- `app/api/routes/debug.py` — `POST /debug/poll-now`, a manual trigger
  that bypasses the market-hours check, gated to `ENVIRONMENT=development`
  only. Built specifically to let the pipeline be verified without
  waiting for the market to be open. **Remove or put real auth in front
  of this before any non-local deployment.**
- `app/main.py` — FastAPI app; `GET /health` is a shallow self-check, real
  per-asset freshness lives in `system_health` for the frontend to read
  directly from Supabase (no custom WebSocket server here — real-time
  delivery to the frontend is expected to go through **Supabase
  Realtime** on the `candles` table, per spec's "Supabase Realtime where
  appropriate").
- `Dockerfile` — for the eventual AWS/VPS/Docker deployment; nothing
  deployed yet, local `uvicorn` only.

**Verified this session, on the user's real machine, against their real
Supabase project:** `pip install -r requirements.txt` succeeded, the
FastAPI app started cleanly, `POST /debug/poll-now` fetched real XAU/USD,
EUR/USD, GBP/USD candles from Twelve Data, wrote them into `candles`
(confirmed via Supabase Table Editor), and wrote `Healthy` rows into
`system_health` for all three assets. This is the first genuinely
end-to-end-tested piece of the whole project — not just "compiles" or
"should work."

**One open data-quality question, not a code bug:** during that test
(run on a Saturday, market closed, via the debug bypass), Twelve Data
returned an identical `open` value across all recent XAU/USD bars in the
raw API response itself (confirmed via temporary raw-payload logging,
since removed) while EUR/USD and GBP/USD opens varied normally. Likely
explanation: gold-specific behavior on Twelve Data's side while the
market is shut, not something in this codebase. **Needs re-checking once
the market is actually open** (Sunday evening UTC onward) — re-run
`POST /debug/poll-now` then and check whether XAU/USD opens vary properly
during real trading. If they still don't, that's a real Twelve Data data
quality problem for gold specifically and may need a different
provider for XAU/USD.

**API credit budget:** see `apps/api/README.md`'s "API credit budget"
section — the default `POLL_INTERVAL_SECONDS=300` for 3 assets is
slightly over Twelve Data's free 800 req/day tier; the README explains
the tradeoffs and a safe default (360s). Now that the pipeline is
verified, avoid further manual `/debug/poll-now` calls outside of the
weekend-reopen data-quality check above — they spend real API credits
for no additional verification value at this point.

## Dashboard home now reads real prices (`apps/web/src/app/dashboard/page.tsx`)

`/dashboard` was still showing the old synthetic "DEMO DATA" banner and
fake prices/regimes even after the Phase 2 collector went live, because
nothing in `apps/web` had been pointed at the new `candles` table yet.
Fixed this session, scoped deliberately narrow (real price only, honest
about everything else):

- `apps/web/src/lib/market-data.ts` (new) — `getAssetPriceSnapshots()`,
  a server-side function that reads the latest and oldest `M5` candle per
  asset directly from Supabase (anon key, RLS-gated, read-only) and
  derives `price`, a 24h `change24hPct`, and a `dataStatus`
  (`LIVE`/`DELAYED`/`STALE`/`OFFLINE`) classified purely by candle age
  per spec section 42. Never throws — any failure (no rows yet, network
  error, etc.) returns `null` for that asset so the page can render an
  honest empty state instead of a fake price.
- `apps/web/src/components/dashboard/asset-signal-card.tsx` — gained two
  optional, backward-compatible props: `regimeAvailable` (renders a plain
  "Not analyzed" badge instead of a fake `RegimeBadge` when the regime
  engine hasn't run) and `dataStatus` (renders the `DataStatusPill`).
  Nothing else that renders this component was found (checked — only
  `dashboard/page.tsx` uses it), so no other page needed changes.
- `apps/web/src/app/dashboard/page.tsx` — rewritten from a client
  component driving fake `generateSignal`/`generateMarketSnapshot` demo
  data into an async Server Component that calls
  `getAssetPriceSnapshots()`. Each asset card now shows the real Supabase
  price and a `NO_TRADE` signal whose `warnings` field says plainly that
  signal analysis isn't available yet (Phase 3/4 not built) — never a
  fabricated CALL/PUT or regime. A new `NoDataCard` fallback renders for
  any asset with no candle rows yet instead of a fake price.

Verified via `npx tsc --noEmit` (only the 3 pre-existing, expected
`@supabase/ssr not installed locally` errors — nothing new) and
`npx next lint` (clean).

Deliberately out of scope this pass: `/dashboard/signals`,
`/dashboard/markets/*`, `/dashboard/analyzer`, `/dashboard/history`,
`/dashboard/performance`, and all `/admin/*` pages still run on the
frontend demo engine (`data/engine.ts`) and still say so — they weren't
touched, since real signal/regime/backtest data depends on Phase 3-5
work that hasn't happened yet. Wiring those to real data before the
signal engine exists would mean inventing fake analysis, which is the
one thing this project explicitly must not do.

## Next recommended step

1. Once the market reopens, re-check the XAU/USD identical-open question
   above — this is the one loose end from Phase 2.
2. `/dashboard` (home) now reads real prices — see above. Extend the same
   pattern to `/dashboard/signals` next, since it's the page every signal
   card links to.
3. Consider adding Supabase Realtime subscriptions on `candles` for the
   live-updating parts of the dashboard, per the "no custom WebSocket
   server" decision above.
4. Regenerate real TypeScript types now that the schema is live:
   `npx supabase gen types typescript --project-id <ref> > apps/web/src/types/database.ts`
   (replacing the `any` placeholder currently there).
5. Let the normal scheduler (not manual polling) run during real trading
   hours to build up genuine candle history for later phases (feature
   engine, backtesting) to work with.
6. The real signal engine (Phase 3-4) is the actual blocker for wiring up
   every other dashboard/admin page honestly — until it exists, those
   pages should keep saying "demo" rather than being half-wired to real
   prices with fake analysis bolted on.
