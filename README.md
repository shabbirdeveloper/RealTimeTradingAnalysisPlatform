# NorthFXTrade

A production-quality web-based Forex signal platform for **manual** Quotex trading.
Analyzes XAU/USD, EUR/USD and GBP/USD and returns CALL / PUT / NO TRADE — it never
places trades automatically.

This repo currently contains **Phase 1: frontend scaffold only** (`apps/web`), built
against the full product spec in the attached Claude project. Backend services
(`services/market-data`, `services/feature-engine`, `services/signal-engine`,
`services/ml-engine`, `services/backtester`), the FastAPI API, and the Supabase
schema/migrations are not implemented yet — see `docs/PHASE-STATUS.md`.

## Getting started

This project was authored without running `npm install` — the sandbox it was built
in has no access to the npm registry. Run these commands yourself in a normal
terminal on this machine:

```bash
cd "apps/web"
npm install
npm run dev
```

Then open http://localhost:3000.

Useful scripts (from `apps/web`):

```bash
npm run dev        # start the dev server
npm run build       # production build (also runs ESLint — see next.config.mjs)
npm run typecheck   # tsc --noEmit
npm run lint         # ESLint only
```

## What's implemented (Phase 1)

- Marketing site: `/`, `/features`, `/performance`, `/pricing`, `/login`,
  `/register`, `/forgot-password`, `/reset-password`, `/disclaimer`, `/privacy`,
  `/terms`.
- Authenticated dashboard shell (sidebar + topbar + mobile nav): `/dashboard` and
  all sub-routes from the spec (`signals`, `signals/[id]`, `markets/[asset]`,
  `analyzer`, `history`, `performance`, `calendar`, `notifications`, `settings`,
  `billing`).
- Admin console shell: `/admin` and its sub-routes (`signals`, `models`,
  `models/[id]`, `backtesting`, `backtesting/compare`, `market-data`, `news`,
  `users`, `subscriptions`, `system`, `logs`).
- A deterministic, seeded **demo data engine** (`src/data/engine.ts`,
  `src/data/history.ts`) that stands in for the real Market Data Collector →
  Feature Engine → Regime Engine → Multi-Timeframe Engine → Signal Engine → Meta
  Model → Calibration pipeline. Every page that shows generated data displays a
  visible **"DEMO DATA"** banner, per the platform's no-fake-data-in-production
  rule. `NO TRADE` is generated as a first-class, common outcome — it is never
  suppressed to make the UI look busier.
- A shadcn/ui-style component library hand-written against Radix primitives
  (`src/components/ui`), since the shadcn CLI itself needs npm registry access.
- Premium dark institutional theme (design tokens in `src/app/globals.css`,
  extended in `tailwind.config.ts`), with dedicated CALL / PUT / NO TRADE / A++
  color semantics.

## What's intentionally NOT implemented yet

- Supabase project, Auth, RLS policies, and database migrations (`supabase/`).
- The FastAPI backend and any real API routes (`apps/api`, listed in section 48 of
  the spec) — the frontend currently reads only from the local demo data engine.
- Real market data ingestion, WebSockets, and the actual feature/regime/ML
  pipeline (`services/*`).
- PWA service worker and push notifications (manifest is wired up; the worker
  itself is deferred to Phase 8 so an untested worker doesn't risk breaking
  caching before there's a backend to test it against).
- Any Quotex integration of any kind — by design, this software never automates
  trade execution.

## Why the source wasn't verified with a real build

This project was generated inside a Claude Code Cowork session whose network
egress policy blocks the npm registry entirely (`registry.npmjs.org` returns
`403 host_not_allowed`), including from the linked-device shell. Every file was
therefore hand-written and passed through local syntax/bracket-balance and
import-resolution checks, but `npm install`, `next build`, `tsc`, and `eslint`
have not actually been run against it. Please run `npm run typecheck && npm run
lint && npm run build` after installing, and report anything that surfaces.
