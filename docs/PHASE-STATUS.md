# Phase status

Tracking against the 10 phases defined in the project spec.

| Phase | Scope | Status |
|---|---|---|
| 1 | Project architecture, database, auth, dashboard, responsive nav, assets, mock UI | Frontend shell done. Database schema written (`supabase/migrations/`, 8 files, all 17 tables + RLS) but not yet applied to a real Supabase project. Auth wiring (`src/lib/supabase/`, `middleware.ts`) is in place and no-ops safely until Supabase env vars are set — not yet connected or tested end-to-end. |
| 2 | Real market-data abstraction, candle storage, WebSocket data flow, feature calculation | Not started |
| 3 | Technical analysis, structure analysis, regime engine, multi-timeframe engine | Simulated in the frontend demo engine only (`apps/web/src/data/engine.ts`) — not a real implementation |
| 4 | Signal engine (CALL/PUT/NO TRADE, expiries, scoring, history) | Simulated in the frontend demo engine only |
| 5 | Backtesting engine, result calculation, analytics | Demo-only backtest builder in the frontend (`buildDemoBacktest`) — not connected to any real historical data or execution logic |
| 6 | ML pipeline, independent models, meta model, probability calibration | Not started. UI already distinguishes `MODEL_NOT_READY` from a calibrated confidence, per spec section 10 |
| 7 | News filter, economic calendar | Frontend UI + static demo calendar data only; no real economic-calendar API integration |
| 8 | Browser/Telegram notifications, PWA | Notification preferences UI built; manifest wired; service worker and real push delivery not implemented |
| 9 | Admin model tools, backtesting comparison, system monitoring | Frontend shells built with demo data; no real backend behind them |
| 10 | Subscription/billing architecture | Frontend billing UI only; no payment provider integration |

## Database schema (written, not yet applied)

`supabase/migrations/` has 8 SQL files covering all 17 tables from spec
section 36, in dependency order:

1. `20260829000001_extensions_and_enums.sql` — pgcrypto + all enum types
2. `20260829000002_core_reference_tables.sql` — profiles, subscriptions, assets, economic_events (+ auto-create-profile-on-signup trigger)
3. `20260829000003_market_data_tables.sql` — candles, market_features (bigint identity PKs — highest-volume tables)
4. `20260829000004_ml_tables.sql` — models, model_versions (only one ACTIVE version per model, enforced by a partial unique index), model_predictions
5. `20260829000005_signals_tables.sql` — signals (spec section 37's exact columns), signal_results
6. `20260829000006_backtesting_tables.sql` — backtests, backtest_signals
7. `20260829000007_notifications_and_system_tables.sql` — notification_preferences (auto-created per user), notifications, system_health, audit_logs
8. `20260829000008_rls_policies.sql` — RLS on every table. Read-only for `authenticated` on market/signal/model data; strictly own-row for profile/subscription/notifications; admin-only (via an `is_admin()` security-definer helper, to avoid the classic self-referential-RLS recursion) for backtests/audit_logs/system_health and the CANDIDATE/REJECTED half of signals. All actual writes are expected to come from the backend via the service-role key, which bypasses RLS — the policies here only cover what the browser is allowed to read/touch directly.

**Not yet done:** this SQL has not been run against a real Postgres — it
passed a structural sanity check (balanced parens/dollar-quotes) but not an
actual `psql`/Supabase SQL editor execution, since no Supabase project is
connected yet and this sandbox has no Postgres to test against. Running it
in the Supabase SQL editor is also the first real syntax check it will get.

## Next recommended step

1. Create a Supabase project, run the 8 migration files above in order
   (Supabase Dashboard -> SQL Editor, or `supabase db push` with the CLI),
   and fix whatever the editor flags (expected on a first real run of SQL
   that's never touched a live database).
2. Add `NEXT_PUBLIC_SUPABASE_URL` / `NEXT_PUBLIC_SUPABASE_ANON_KEY` to
   `apps/web/.env.local` (see `apps/web/.env.example`) — the app will start
   using them automatically since `src/lib/supabase/client.ts` /
   `server.ts` / `middleware.ts` are already wired, but nothing has swapped
   from demo data to real Supabase queries yet.
3. Swap the frontend's demo data calls for real queries one page at a time —
   starting with `/dashboard` and `/dashboard/signals`, since those are the
   pages every other view links back to.
4. Regenerate real TypeScript types once the schema is live:
   `npx supabase gen types typescript --project-id <ref> > apps/web/src/types/database.ts`
   (replacing the `any` placeholder currently there).
