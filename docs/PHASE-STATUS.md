# Phase status

Tracking against the 10 phases defined in the project spec.

| Phase | Scope | Status |
|---|---|---|
| 1 | Project architecture, database, auth, dashboard, responsive nav, assets, mock UI | Frontend shell done. Database schema applied to a real Supabase project (confirmed — see below). Auth is wired for real and confirmed live. `/dashboard`, `/dashboard/signals`, and `/dashboard/markets/[asset]` now read real prices AND real signals from Supabase — see "Real signal engine" below. `/dashboard/history`, `/dashboard/performance`, `/dashboard/analyzer`, and all of `/admin/*` still run the frontend demo engine, honestly, pending Phase 5 (backtesting/resolution) and Phase 6 (ML). |
| 2 | Real market-data abstraction, candle storage, WebSocket data flow, feature calculation | **Confirmed working end-to-end** — `apps/api/` (Python/FastAPI) fetches real M5 candles from Twelve Data, derives M15/H1/H4 in-process, writes both into `candles`, and reports per-asset status into `system_health`. Feature calculation (spec section 6) is now real too — see Phase 3 below. |
| 3 | Technical analysis, structure analysis, regime engine, multi-timeframe engine | **Real, rule-based implementation** in `apps/api/app/features/` — computed from real stored candles on every poll cycle. See "Real signal engine" below for exactly what is and isn't real yet. |
| 4 | Signal engine (CALL/PUT/NO TRADE, expiries, scoring, history) | **Real, rule-based decision engine** (`apps/api/app/features/signal_engine.py`) writing into the real `signals` table. Expiry scoring is real; the meta trade/no-trade model (spec section 12) and calibrated confidence are not — see below. Signal resolution (spec section 49 — marking WON/LOST/DRAW at expiry) is not built yet, so history/performance still can't be computed from real outcomes. |
| 5 | Backtesting engine, result calculation, analytics | **Real.** Signal resolution (`app/collector/resolution.py`, spec section 49) marks signals WON/LOST/DRAW at expiry against the real closing price. The historical backtester (`app/backtesting/`, spec section 13) replays the real signal engine over stored candles with an enforced no-look-ahead guarantee, and `/admin/backtesting` reads real runs. Both are honestly limited by how much real candle history exists — see "Backtesting engine" below. |
| 6 | ML pipeline, independent models, meta model, probability calibration | Not started. UI already distinguishes `MODEL_NOT_READY` from a calibrated confidence, per spec section 10 |
| 7 | News filter, economic calendar | **Blackout logic is real and tested** (`apps/api/app/news/`) — pre-news pause, NEWS_MODE, post-event stabilization, configurable windows, asset↔currency relevance, wired into the signal engine. `/dashboard/calendar` and `/admin/news` read the real `economic_events` table. **No calendar data provider is connected yet** — that needs a provider choice and is the one remaining piece; the system says so loudly rather than implying it's protected. See "News filter" below. |
| 8 | Browser/Telegram notifications, PWA | **Mostly real.** Preferences now load/save against Supabase; service worker with app-shell-only caching + offline page; install prompt; browser alerts fire on new qualifying signals **while the app is open**. Background push (app closed) needs a push server, and Telegram needs a bot token — both explicitly stated in the UI rather than implied. See "PWA + notifications" below. |
| 9 | Admin model tools, backtesting comparison, system monitoring | **Mostly real.** `/admin/signals`, `/admin/market-data`, `/admin/system`, `/admin/backtesting`, `/admin/users` and `/admin/logs` all read real data, and audit logging now actually writes (spec section 38). `/admin/models` and `/admin/backtesting/compare` remain demo — both need trained ML models (Phase 6). |
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

## Audit logging + admin users/logs

Closes a stated security gap and two of the last demo pages.

**Audit logging (spec section 38).** `audit_logs` existed as a table with
nothing writing to it. `app/storage/audit_repository.py` now records the
events an operator actually needs: backtest created/completed/failed,
market-data fetch failures, analysis-cycle failures, and signal-resolution
batches.

Two deliberate scoping calls:
- **Individual signals are not audited.** They are already first-class
  rows in `signals` — including the rejected ones — and echoing them into
  the audit log would bury the operational events it exists to surface.
- **Every write is best-effort and swallows its own errors.** A collector
  that dies because it couldn't write a log line is strictly worse than
  one that keeps collecting with a gap in the log.

`actor_user_id` is null on nearly everything, and that is honest rather
than lazy: this service authenticates with a shared admin secret, not a
user session, so there is no verified identity to attribute an action to.
Recording a guess would be worse than recording nothing. The UI labels
those entries "System".

**`/admin/users` and the security-definer function.** Emails live in
`auth.users`, which the browser's anon key cannot read — by design. The
alternative to a hardened function would have been shipping the
service-role key to the frontend, which would hand the browser
unrestricted access to every table. Instead, migration
`20260830000013` adds one read-only `admin_list_users()` function:
- `SECURITY DEFINER` with a **pinned `search_path`**, so a caller cannot
  shadow `profiles` or `auth.users` with their own objects and redirect
  the query.
- The **admin check lives inside the function body and raises** (42501).
  Trusting the caller to check first would let any authenticated user
  invoke it over PostgREST and read every email.
- `EXECUTE` revoked from `public`/`anon`, granted only to
  `authenticated`. Read-only: it exposes no path to change a role or plan.
- Every table reference is schema-qualified *and* the `is_admin()` call is
  qualified — two independent barriers, so the protection survives someone
  later relaxing the `search_path` line.

The page is deliberately read-only. A role change is a privilege-escalation
path and deserves a deliberate, audited action rather than an inline
toggle; plans stay read-only until a payment provider exists.

**`/admin/logs`** renders the real entries with human labels, failure
actions highlighted, and an honest empty state explaining that entries
appear as the service runs.

Verified: 115 Python tests passing, `tsc --noEmit` and `next lint` clean,
plus a scripted check of the migration asserting the admin check is
present and qualified, `search_path` is pinned, `anon` is revoked,
`authenticated` is granted, and the function contains no write statements.

## PWA + notifications (Phase 8)

For manual binary trading, alert latency effectively *is* the product — a
15-minute expiry seen 20 minutes late is worthless. So this phase matters
more here than in a typical app.

**What's real:**
- **Preferences actually persist.** `/dashboard/notifications` was
  `useState`-only; it now loads and saves `notification_preferences`
  through `lib/notification-preferences.ts`, auto-saving on toggle with
  visible saving/saved/error states. RLS scopes every row to its owner, so
  this runs safely from the browser with the anon key.
- **Service worker** (`public/sw.js`) built around one rule from spec
  section 27: **cache the app shell, never trading data.** A cached price
  is worse than no price — a trader glancing at an offline dashboard
  showing yesterday's gold quote could place a real trade on it. So every
  navigation and data request is network-first, Supabase and `/api/*` are
  never cached at all, and offline shows an explicit page stating that no
  prices are displayed *on purpose*. Only content-hashed build assets are
  cache-first, where staleness is meaningless.
- **Install prompt** (`components/shared/pwa-provider.tsx`), dismissal
  remembered in localStorage. SW registers in production only — in dev it
  would cache assets that change on every edit.
- **Browser alerts** fire on new qualifying signals, de-duplicated by
  signal id so re-renders and multiple open tabs can't double-notify.

**The honest scope limit, stated in the UI itself:** these use the
Notification API directly, so they fire only while NorthFXTrade is
actually open — a background tab or the installed window both count, a
fully closed app does not. True background delivery needs Web Push (VAPID
keypair, stored push subscriptions, a server that sends them). The
settings page says this plainly rather than implying alerts arrive when
they can't, and `sw.js` deliberately has **no** `push` handler — adding
one with no server to trigger it would be a handler that can never fire.

**A gap this surfaced and closed:** with only A++/A+ toggles the whole
feature would have been dead code, because the engine caps grades at B
until a calibrated ML model exists (spec section 10) — no alert could
ever have fired. Migration `20260830000012` adds a `bgrade_enabled`
column, **defaulting to false**: opt-in, because a B is explicitly not a
high-conviction setup and alerting on it by default would train the user
to ignore alerts. The toggle's own description says it is currently the
only grade the engine can produce.

The same migration adds `btcusd_enabled` / `ethusd_enabled` — adding
crypto had left the per-asset toggles missing exactly the two assets that
trade at the weekend, when a trader is most likely to be away from the
screen.

**Still not built (Phase 8 remainder):** Web Push background delivery,
Telegram delivery (needs a bot token from the user), and email delivery.
The `notifications` table exists but nothing writes to it yet — an
in-app notification feed is a natural next step and needs no external
dependency.

Verified: `tsc --noEmit` and `next lint` clean, `node --check` on the
service worker, 115 Python tests still passing (unchanged — this phase is
frontend-only).

## 24/7 coverage: crypto assets + the OTC guard

Prompted by a direct question — "which market is open all the time?" —
which surfaced a genuine architectural risk worth recording.

**The risk.** Forex and gold close from roughly Friday 22:00 UTC to
Sunday 21:00 UTC, so the platform had nothing real to analyse all
weekend. Binary brokers fill that gap with "OTC" instruments (e.g.
"EUR/USD OTC") that stay open 24/7. **Those are not real markets** —
they are synthetic price series generated by the broker, which does not
publish how the values are derived.

That matters more than it first appears. This platform analyses real
Twelve Data prices; the user then places the trade manually on the
broker. If the trade is placed on an OTC instrument, the series analysed
and the series that settles the trade are unrelated — while the signal
still renders as a confident, graded, A-tier-looking result. It is the
single most dangerous failure mode available to this system, because
nothing about it *looks* broken. The spec also forbids sourcing
broker-side prices (no scraping, no undocumented API), so there is no
honest way to analyse OTC instruments at all.

**The two responses:**

1. **Real 24/7 coverage — crypto.** Added BTCUSD and ETHUSD (migration
   `20260830000011`). Crypto trades continuously on real exchanges, so it
   gives genuine weekend coverage through the same real-data pipeline. The
   spec's "support additional pairs without major refactoring" goal held
   up: this was enum + config + seed rows, with no engine changes.
   - `market_hours.is_market_open()` is now **per-asset** — crypto never
     closes, forex keeps the Friday/Sunday window. The scheduler skips
     per-asset rather than per-cycle; a single global check would either
     blind crypto on Saturday or waste credits re-fetching closed-market
     forex candles. `asset=None` still defaults to the *forex* schedule,
     so a caller that forgets to pass an asset fails closed, never
     "always open".
   - Instrument classification lives in `app/instruments.py` rather than
     beside the pydantic `Asset` enum, so the market-hours logic stays
     dependency-free and unit-testable.

2. **The OTC guard.** `app/instruments.py::assert_real_market_symbol()`
   is called at the top of `build_signal()` and **raises** on anything
   that looks like a broker OTC/synthetic instrument. Raising rather than
   returning NO_TRADE is deliberate: a caller that ignores a boolean fails
   open, and failing open here means emitting a confident signal about a
   series the user isn't trading. Detection is intentionally conservative
   (a false rejection costs one config fix; a false acceptance costs real
   money on a meaningless signal) and covers `-OTC`, `(OTC)`, `_otc`,
   synthetic families like "Volatility 75 Index" / "Boom 1000", while not
   false-positiving on substrings.
   `components/shared/otc-warning.tsx` is the human half of the same
   guard, shown on the Dashboard and Live Signals pages — where the
   mistake would actually be made.

**API budget consequence, computed not guessed.** Five assets on two
schedules changes the math: at the old 300s interval that is ~1,198
requests/day against Twelve Data's 800/day free tier, so the collector
would have started failing partway through each day. Break-even is ~450s;
**the default is now 600s** (~599/day). The table is in
`apps/api/README.md`.

**News relevance for crypto** is a deliberate approximation: USD releases
are treated as relevant (crypto does react to US rates/CPI), but this is
a conservative "pause around big USD prints", not a claim that crypto
behaves like a dollar pair.

Verified: 115 tests passing (up from 95 — 20 new across the guard,
per-asset market hours, and the classification), `tsc --noEmit` and
`next lint` clean. TypeScript caught two hardcoded per-asset records
during this change; both were rewritten to derive from `ASSET_LIST` so
adding an asset can't silently leave a key missing again.

## News filter (Phase 7) — `apps/api/app/news/`

Spec section 8's news protection, built in two halves: the policy (done,
real, tested) and the data feed (not connected — needs a provider
decision).

**What's real and running:**
- `blackout.py` — pure, dependency-free policy. Pre-news pause →
  NEWS_MODE at the release → post-event stabilization window, with
  configurable durations (spec section 8 requires configurability
  explicitly). 22 unit tests covering window boundaries, impact
  filtering, and misuse.
- **Asset↔currency relevance**, which is the part that's easy to get
  wrong: USD news moves all three instruments; EUR news only EURUSD; GBP
  news only GBPUSD. Gold is quoted in USD, so a US CPI print is a
  gold-relevant event even though "XAU" contains no currency code — this
  is tested explicitly.
- Wired into `build_signal()`: an active blackout returns NO_TRADE with
  `market_regime = NEWS_MODE` and a trader-readable reason naming the
  event, overriding everything else. The multi-timeframe read is still
  reported during a pause — you can see the market, you just get no
  signal. Tests confirm the *same* history that produces a CALL with no
  news produces a NEWS_MODE NO_TRADE with news pending, so the pause is
  demonstrably caused by the filter and not by weak conditions.
- Migration `20260830000010` adds a natural-key unique constraint
  (event_name, currency, event_time) to `economic_events`. Without it, a
  provider re-fetching the same window — which it must, since `actual`
  only exists after the release — would duplicate the whole calendar
  every refresh.
- `/dashboard/calendar` and `/admin/news` read the real table.

**The one deliberate seam: `calendar_available` is separate from the
event list.** An empty list from an unconfigured provider means *"we have
no calendar"*; an empty list from a working provider means *"nothing is
scheduled"*. Collapsing those two would silently turn an unprotected
system into one that looks protected — a clean, empty calendar page
implying the day is clear is exactly the kind of false safety this
project must not ship. So `NullCalendarProvider` reports
`is_configured = False`, every signal carries a loud "high-impact news is
NOT being screened — check the calendar yourself" warning, and the
calendar page says plainly that this is not an empty day.

**Why no provider is implemented:** the surveyed options are either paid
(Trading Economics, FinanceFlow) or third-party scrapers of sites whose
terms don't clearly permit it. Hard-wiring a fragile or questionable
source into the trading path was the wrong call to make unilaterally —
it's a cost and compliance decision. **This is the single remaining piece
of Phase 7, and it is now a one-class change:** implement
`fetch_upcoming()` in a subclass of `EconomicCalendarProvider`
(`app/news/base.py`), return tz-aware UTC events, and select it in
`app/news/factory.py`. Nothing else in the system changes — storage,
policy, engine wiring and UI are all done.

**Blackout defaults are conventional, not validated:** 30 minutes either
side. Like the indicator weights, these should be tested against real
history with the backtester rather than trusted.

Verified: 95 tests passing (up from 67 — 28 new), `tsc --noEmit` and
`next lint` clean, and all 76 internal `app.*` imports statically
resolved.

## Backtesting engine (Phase 5) — `apps/api/app/backtesting/`

Replays the real signal engine over stored candle history and measures
how the rules would actually have performed. This is what makes the
indicator/regime weights (flagged elsewhere as unvalidated starting
guesses) testable rather than permanent assumptions.

**The no-look-ahead guarantee**, which is the whole reason a backtester
is worth anything (spec section 13: "Do NOT use look-ahead bias. Do NOT
use future data in feature calculation."):

- `replay.py` reduces it to one rule, enforced in one place: *at
  simulated time T, only candles that had already CLOSED at T exist.*
  The filter is `open_time + timeframe_duration <= as_of`, never
  `open_time <= as_of` — an H4 bar opening at 12:00 tells you nothing at
  13:00, and treating it as visible would leak up to four hours of
  future price into a decision.
- `tests/test_replay.py` proves it: one test builds a clean uptrend,
  records the decision at a timestamp, then violently corrupts every bar
  after that timestamp to 999999.0 and asserts the decision is
  bit-for-bit identical (direction, score, regime, chosen expiry, entry
  price, and every per-expiry candidate). A guard test first asserts the
  fixture produces a real accepted CALL — otherwise the spike test could
  pass trivially by short-circuiting on insufficient data.

**Design choices that keep the numbers meaningful:**
- It calls the same `build_signal()` the live collector calls. There is
  no separate "backtest strategy" that could drift from what actually
  runs in production.
- It resolves outcomes with the same rule as the live resolution job
  (close of the first M5 candle at/after expiry; equal price = DRAW), so
  backtest and live results are directly comparable. Both share the same
  documented approximation — that close is up to 5 minutes past the
  exact expiry moment — rather than differing silently.
- An accepted signal whose expiry falls past the end of stored history
  is counted as **unresolved**, never guessed, and the run reports how
  many.
- `build_signal()` gained a `technical_score_threshold` parameter purely
  so the backtester can sweep it (spec section 32's "minimum
  confidence" input) without duplicating any strategy logic.

**A real bug this surfaced:** `atr_percentile()` counted ties as
"below", so a perfectly flat-volatility market scored at the 100th
percentile and the regime engine called it HIGH_VOLATILITY — exactly
backwards, and it would have suppressed signals in calm markets. Now
uses the standard midpoint tie convention (steady volatility reads as
50). Found only because the backtest fixture produced constant-range
candles; regression test added.

**Naming honesty:** the schema column is `min_confidence` and spec
section 32 calls the input "minimum confidence", but there is no
calibrated model confidence to threshold on (Phase 6). The API field is
named `min_technical_score` and the UI labels it "Min technical score",
because calling it confidence would imply a model that doesn't exist.

**API** (spec section 48): `POST /admin/backtests` queues a run in a
background task (a long replay shouldn't hold a request open) and
`GET /admin/backtests/{id}` polls it; rows move PENDING → RUNNING →
COMPLETED/FAILED, so a crash leaves a FAILED row with its error rather
than a stuck PENDING one.

**Auth caveat, stated plainly:** `apps/api` has no user auth of its own
— it holds the Supabase service-role key and is meant to sit on a
private network. The admin endpoints check a shared secret
(`ADMIN_API_KEY`, sent as `X-Admin-Api-Key`) and **fail closed**: with
no key configured they refuse every request rather than defaulting open.
That is a minimum bar, not a real auth system. Anything internet-facing
needs a proper auth layer in front of this service.

**What a backtest can and cannot tell you right now:** it can only cover
candle history that has actually been collected, which is currently very
little. A run over a few days is a smoke test of the rules — it proves
the pipeline works and catches obvious breakage. It is *not* evidence of
accuracy, and the UI says so. Spec section 15's bar (sufficient verified
unseen results) is a matter of accumulated real time, not more code.

Verified: 67 tests passing (up from 43 — 24 new across `test_replay.py`
and `test_backtest_engine.py`), `tsc --noEmit` and `next lint` clean, and
a static check confirming all 69 internal `app.*` imports resolve to real
symbols (neither sandbox can reach PyPI, so a live FastAPI import test
wasn't possible from here — **restarting `apps/api` on your machine is
still the real first run**).

## Signal resolution + History/Performance/Analyzer/Admin wired to real data

Third round this session, after the user asked why the remaining pages
(Performance screenshot specifically) were still demo. The honest answer
for Performance/History specifically was "there's no shortcut — a real
accuracy number needs real signals to actually expire and get checked,"
so this round built exactly that:

- `apps/api/app/collector/resolution.py` (new) + a new
  `fetch_first_candle_at_or_after()` in `candle_repository.py`:
  `resolve_expired_signals()` runs every poll cycle (wired into
  `scheduler.py`, isolated so a resolution failure can't block candle
  collection), finds ACTIVE directional signals whose `expiry_at` has
  passed, looks up the real candle at/after that time (with its real
  `source`), and marks WON/LOST (equal price → DRAW), writing both the
  `signals` row and a `signal_results` audit row. A signal with no real
  candle yet at/after its expiry is left alone for the next cycle —
  never resolved from a guess.
- `apps/web/src/lib/performance.ts` — real KPIs (wins/losses/accuracy/
  streaks) and breakdowns (by asset/expiry/session/regime/technical-score
  bucket — bucketed by Technical Score, not calibrated confidence, since
  that still doesn't exist) computed from real `WON`/`LOST`/`DRAW` rows.
  Wired into `/dashboard/performance`, which now says plainly when
  nothing has resolved yet rather than showing fake 420/75.1%/etc.
- `apps/web/src/lib/history.ts` — every real signal row this user can
  see (RLS-gated), with `PENDING` shown for anything not yet resolved.
  Wired into `/dashboard/history`, same filter UI as before, real data.
- `apps/web/src/components/dashboard/analyzer-view.tsx` — `/dashboard/analyzer`
  now picks from the latest real signal per asset and its real per-expiry
  candidates instead of generating a new demo signal on every render.
- `apps/web/src/lib/admin.ts` — `/admin/signals` now shows real accepted
  signals and real rejected opportunities (spec section 30 — a
  directional bias that never cleared the B-grade threshold, admin-only
  via RLS). `/admin/market-data` shows real `system_health` +
  last-real-candle time per asset, with missing-candle and API-error
  tracking honestly labeled "not tracked yet" instead of a fabricated
  zero that would imply monitoring exists. `/admin/system` shows real
  `system_health` rows for the components that actually report
  (`market_data.*`) and labels every other spec-named component (API,
  Database, Feature Engine, ML Engine, News API, ...) "Not monitored"
  rather than guessing Healthy.

**Explicitly still demo/blocked, not faked, because each needs
something this pass doesn't have:**
- `/dashboard/calendar`, `/admin/news` — need a real economic-calendar
  API integration (Phase 7). Needs a provider/API-key decision from the
  user.
- `/admin/backtesting`, `/admin/models`, `/admin/backtesting/compare` —
  need the real historical backtesting engine (Phase 5's
  `/admin/backtesting` specifically, distinct from resolution above) and
  trained ML models (Phase 6). Substantial builds, not swaps.
- `/dashboard/billing`, `/admin/subscriptions` — need a real payment
  provider integration (Phase 10). Needs a provider decision from the
  user (e.g. Stripe).
- `/admin/users` — could read real `profiles` rows (the table already
  exists and is populated by the signup trigger) but wasn't in this
  pass's scope; a reasonable quick win for a future session.
- `/admin/logs` — `audit_logs` table exists but nothing writes to it yet;
  would need audit logging added across the app's mutating actions.

Verified: `python -m unittest discover` (43/43, unchanged — resolution
logic isn't independently unit tested this round since it's a thin
Supabase read/write wrapper, same testing posture as the rest of
`app/storage/`), `npx tsc --noEmit` (only the 3 pre-existing
`@supabase/ssr` errors), `npx next lint` (clean). **Not yet run against
the live Supabase project** — same next-action as the signal engine
above: push, restart `apps/api`, let it run.

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
   signal engine and backtesting code. Set `ADMIN_API_KEY` in
   `apps/api/.env` first, or the backtest endpoints will refuse to run
   (by design — they fail closed).
2. Run migrations `20260830000010` (calendar natural key), `20260830000011`
   (BTC/USD + ETH/USD), `20260830000012` (crypto + B-grade alert toggles)
   and `20260830000013` (admin user-listing function) in the Supabase SQL
   editor. `apps/api/.env` already has `POLL_INTERVAL_SECONDS=600` and a
   generated `ADMIN_API_KEY`.
   Then trigger one poll cycle (`POST /debug/poll-now`, or wait for the
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
8. **Pick an economic calendar data provider.** The entire news filter
   is built and tested; only the feed is missing, and it's a one-class
   change (`app/news/base.py` documents exactly what). Until then every
   signal correctly warns that news is unscreened. This is the highest-
   value remaining decision because it's blocking finished work.
9. Phase 6 (ML) is the other standing gap the engine warns about on every
   decision. It needs real resolved-signal history to train against, so
   it comes after enough time has passed for that to accumulate.
10. Once a few weeks of real candle history exists, use the backtester to
    validate the signal engine's weights, thresholds, AND the news
    blackout windows instead of leaving them as the starting guesses they
    currently are. That is the single highest-value use of the
    backtester, and the reason it was built before the ML phase.
11. Remaining demo surfaces, in rough priority order: `/admin/models` +
    `/admin/backtesting/compare` (Phase 6), `/dashboard/billing` +
    `/admin/subscriptions` (Phase 10, needs a payment provider),
    `/admin/users` (cheap — real `profiles` data already exists),
    `/admin/logs` (needs audit logging wired up).
