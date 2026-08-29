# Phase status

Tracking against the 10 phases defined in the project spec.

| Phase | Scope | Status |
|---|---|---|
| 1 | Project architecture, database, auth, dashboard, responsive nav, assets, mock UI | Frontend shell done. Database schema applied to a real Supabase project (confirmed — see below). Auth is wired for real and confirmed live. `/dashboard`, `/dashboard/signals`, and `/dashboard/markets/[asset]` now read real prices AND real signals from Supabase — see "Real signal engine" below. `/dashboard/history`, `/dashboard/performance`, `/dashboard/analyzer`, and all of `/admin/*` still run the frontend demo engine, honestly, pending Phase 5 (backtesting/resolution) and Phase 6 (ML). |
| 2 | Real market-data abstraction, candle storage, WebSocket data flow, feature calculation | **Confirmed working end-to-end** — `apps/api/` (Python/FastAPI) fetches real M5 candles from Twelve Data, derives M15/H1/H4 in-process, writes both into `candles`, and reports per-asset status into `system_health`. Feature calculation (spec section 6) is now real too — see Phase 3 below. |
| 3 | Technical analysis, structure analysis, regime engine, multi-timeframe engine | **Real, rule-based implementation** in `apps/api/app/features/` — computed from real stored candles on every poll cycle. See "Real signal engine" below for exactly what is and isn't real yet. |
| 4 | Signal engine (CALL/PUT/NO TRADE, expiries, scoring, history) | **Real, rule-based decision engine** (`apps/api/app/features/signal_engine.py`) writing into the real `signals` table. Expiry scoring is real; the meta trade/no-trade model (spec section 12) and calibrated confidence are not — see below. Signal resolution (spec section 49 — marking WON/LOST/DRAW at expiry) is not built yet, so history/performance still can't be computed from real outcomes. |
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

## Real signal engine (Phases 3 + 4) — `apps/api/app/features/`

Follow-up in the same session, in response to "I need all demo replaced
with real data." This replaces the frontend's random demo engine
(`data/engine.ts`) with a genuine, rule-based technical analysis +
market structure + regime + multi-timeframe + signal engine, computed
from real stored candles on every collector poll cycle, wired into
`/dashboard`, `/dashboard/signals`, and `/dashboard/markets/[asset]`.

**What's real now:**
- `app/features/indicators.py` — EMA20/50/200 (+ slope), RSI14 (+ slope),
  MACD(12,26,9) + histogram, ATR14 (+ percentile vs recent history),
  Bollinger(20,2). Pure functions, no randomness, computed from real
  candle history. Each returns `None` — not a partial or estimated value
  — when there isn't yet enough real history to compute it honestly.
  27 unit tests.
- `app/features/structure.py` — real swing high/low detection (2-bar
  fractal), HH/HL/LH/LL sequence classification, break of structure,
  change of character, support/resistance, plus real session detection
  and Asian/London high-low ranges computed from actual candle
  timestamps. 10 unit tests.
- `app/features/regime.py` — classifies TRENDING_UP/DOWN, RANGING,
  HIGH_VOLATILITY, LOW_VOLATILITY, or UNSTABLE from real H1 ATR
  percentile + EMA slope + structure. **NEWS_MODE is never returned** —
  classifying it correctly needs the economic calendar (Phase 7), which
  doesn't exist yet; returning it without real calendar data would be
  exactly the fake-signal problem this project must avoid.
- `app/features/timeframe_bias.py` — real BULLISH/BEARISH/NEUTRAL bias
  per timeframe (H4/H1/M15/M5) from EMA structure + RSI + MACD + swing
  structure, with an explicit `insufficient_data` flag rather than a
  guess when a timeframe doesn't have enough history yet.
- `app/features/signal_engine.py` — combines all of the above into a
  real CALL/PUT/NO_TRADE decision with a genuinely-computed Technical
  Score (0-100) and per-expiry (15/30/60m) candidates, weighted toward
  fast timeframes for 15m and slow timeframes for 60m. 5 unit tests,
  including one that asserts the engine can never return a grade above B
  — see the honest limits below.
- Writes into the real DB tables from the original schema: per-cycle
  feature snapshots into `market_features` (`app/storage/feature_repository.py`)
  and one `signals` row per asset per poll cycle
  (`app/storage/signal_repository.py`). `apps/web/src/lib/signals.ts` and
  `apps/web/src/lib/features.ts` read them back for the dashboard, live
  signals page, and market detail page — replacing `generateSignal()` /
  `generateTechnicalMetrics()` / `generateStructureNotes()` wherever real
  data exists, falling back to the labeled demo engine (with an explicit
  "no real signal/feature yet" note) wherever it doesn't yet.

**Honest limits, deliberately not worked around:**
- **No calibrated ML confidence.** Phase 6 (XGBoost/LightGBM/calibration)
  isn't built — there's no trained model to produce one. `raw_probability`
  and `calibrated_confidence` are always `null`, and grade is capped at
  B (or REJECTED) — never A/A+/A++ — exactly matching spec section 10's
  rule and the frontend's own pre-existing `gradeFromConfidence()` logic
  for the `MODEL_NOT_READY` case. The signal engine states this in an
  explicit warning on every decision rather than a footnote.
- **No meta trade/no-trade model.** Spec section 12's separate TAKE/REJECT
  model doesn't exist yet either — also stated as an explicit warning,
  not silently skipped.
- **No economic calendar / news filter.** Spec section 8 needs Phase 7's
  calendar integration; every signal states this limitation explicitly
  rather than silently ignoring news risk.
- **Real history is currently thin.** The collector only started writing
  real candles this session, and the market has been closed for most of
  that time. EMA200 needs 200 real H4 candles (~33 days); until enough
  real history accumulates, most assets/timeframes will honestly return
  `insufficient_data` → NO_TRADE rather than analyze on too small a
  sample. This is the system working as designed, not a bug — it will
  naturally produce richer, real analysis as more real candles land over
  the coming days/weeks with the market open.
- **Indicator/regime weights (vote thresholds, the 78-point B cutoff,
  per-expiry weighting) are a reasonable starting rule set, not a
  backtested-optimal one.** Validating and tuning them against real
  historical outcomes is explicitly the backtesting engine's job (spec
  section 13) once enough real signal history exists — noted in code
  comments in `timeframe_bias.py` and `signal_engine.py`.
- **No signal resolution job yet** (spec section 49 — marking a signal
  WON/LOST/DRAW once its expiry passes by checking the real closing
  price). Without it, `/dashboard/history` and `/dashboard/performance`
  can't be computed from real outcomes yet, so those two pages
  deliberately stay on the demo engine — building the resolution job is
  the natural next step once enough signals have expiry timestamps in
  the past to resolve.

Verified via `python3 -m unittest discover -s tests -t .` (43/43
passing, up from 12) and, on the frontend, `npx tsc --noEmit` (only the
3 pre-existing `@supabase/ssr` errors) and `npx next lint` (clean). Not
yet verified end-to-end against a live poll cycle on the user's machine
(the pattern used for Phase 2) — that requires restarting the `apps/api`
process so it picks up this code, then either waiting for the next
scheduled poll or calling `/debug/poll-now`, then checking Supabase's
`market_features` and `signals` tables for new rows. **This is the
user's next action**, alongside pushing this commit (see the push
constraint above).

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
`/dashboard/analyzer`, `/dashboard/history`, `/dashboard/performance`,
and all `/admin/*` pages still run on the frontend demo engine
(`data/engine.ts`) and still say so — they weren't touched, since real
signal/regime/backtest data depends on Phase 3-5 work that hasn't
happened yet. Wiring those to real data before the signal engine exists
would mean inventing fake analysis, which is the one thing this project
explicitly must not do.

## Market detail pages also wired to real price (`/dashboard/markets/[asset]`)

Follow-up in the same session: the per-asset market pages
(`/dashboard/markets/xauusd` etc.) were still showing the old blanket
"DEMO DATA" banner over a fully-synthetic price, since only the
dashboard home page had been wired above. Same treatment, applied
consistently:

- `apps/web/src/lib/market-data.ts` — added `getAssetPriceSnapshot(asset)`
  for a single-asset lookup (shares the fetch logic with
  `getAssetPriceSnapshots()` via a new `fetchSnapshotForAssetId` helper),
  so the per-asset page doesn't pull all three assets' candles just to
  show one.
- `apps/web/src/app/dashboard/markets/[asset]/page.tsx` — fetches the
  real snapshot server-side, passes it to `MarketPageContent`.
- `apps/web/src/components/dashboard/market-page-content.tsx` — Price,
  24h change, and the `DataStatusPill` now use the real snapshot when
  one exists; falls back to the demo-generated price only if no candles
  exist yet for that asset. Session (a pure function of UTC time, not
  fabricated) was already accurate even in demo mode. Everything else —
  H4 bias badge, multi-timeframe bias grid, regime badge, technical
  indicators, market structure notes, current signal, expiry-candidate
  table, signal history table, performance stats — is still the demo
  engine, unchanged. The banner was rewritten to say exactly which half
  of the page is real (price/change) vs still a placeholder, instead of
  a blanket "DEMO DATA" claim that would now be inaccurate for the price
  row. When no real snapshot exists yet for an asset, the page falls
  back to the original full `DemoDataBanner`.

Verified via `npx tsc --noEmit` (same 3 pre-existing `@supabase/ssr`
errors, nothing new) and `npx next lint` (clean). Committed locally
(`513dd56`) — **push is the user's next action**, same push restriction
as above.

## Next recommended step

1. **Push the latest commits** (see the push constraint noted above —
   this session can commit locally but can't push) and restart the
   `apps/api` process on your machine so it picks up the new feature/
   signal engine code.
2. Trigger one poll cycle (`POST /debug/poll-now`, or wait for the
   scheduler) and confirm real rows appear in Supabase's
   `market_features` and `signals` tables — the same "verify it actually
   ran, don't just trust that it compiles" pattern used for Phase 2.
   Expect mostly `NO_TRADE` / `insufficient_data` results at first — real
   history is still thin (see "Real history is currently thin" above).
3. Once the market reopens, re-check the XAU/USD identical-open question
   from Phase 2 alongside the new signal engine's first real reads.
4. Let the scheduler run continuously during real trading hours so real
   candle + feature history actually accumulates — every honest limit
   above (insufficient_data, EMA200 warm-up) resolves itself with time
   and real data, not more code.
5. Build the signal resolution job (spec section 49): mark ACTIVE
   signals WON/LOST/DRAW once `expiry_at` passes, using the real closing
   price. This unlocks real `/dashboard/history` and
   `/dashboard/performance` — currently the two biggest remaining demo
   surfaces.
6. Consider adding Supabase Realtime subscriptions on `candles`/`signals`
   for live-updating dashboard pieces, per the "no custom WebSocket
   server" decision above.
7. Regenerate real TypeScript types now that the schema is live:
   `npx supabase gen types typescript --project-id <ref> > apps/web/src/types/database.ts`
   (replacing the `any` placeholder currently there).
8. Phase 6 (ML) and Phase 7 (news/calendar) are the two remaining honest
   gaps the signal engine explicitly warns about on every decision —
   tackle news/calendar first (it's a data-integration problem); ML
   needs real resolved-signal history from step 5 to train against
   first, so it naturally comes after.
