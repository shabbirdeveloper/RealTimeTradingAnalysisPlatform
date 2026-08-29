# Phase status

Tracking against the 10 phases defined in the project spec.

| Phase | Scope | Status |
|---|---|---|
| 1 | Project architecture, database, auth, dashboard, responsive nav, assets, mock UI | Frontend shell done. Database/auth not started. |
| 2 | Real market-data abstraction, candle storage, WebSocket data flow, feature calculation | Not started |
| 3 | Technical analysis, structure analysis, regime engine, multi-timeframe engine | Simulated in the frontend demo engine only (`apps/web/src/data/engine.ts`) — not a real implementation |
| 4 | Signal engine (CALL/PUT/NO TRADE, expiries, scoring, history) | Simulated in the frontend demo engine only |
| 5 | Backtesting engine, result calculation, analytics | Demo-only backtest builder in the frontend (`buildDemoBacktest`) — not connected to any real historical data or execution logic |
| 6 | ML pipeline, independent models, meta model, probability calibration | Not started. UI already distinguishes `MODEL_NOT_READY` from a calibrated confidence, per spec section 10 |
| 7 | News filter, economic calendar | Frontend UI + static demo calendar data only; no real economic-calendar API integration |
| 8 | Browser/Telegram notifications, PWA | Notification preferences UI built; manifest wired; service worker and real push delivery not implemented |
| 9 | Admin model tools, backtesting comparison, system monitoring | Frontend shells built with demo data; no real backend behind them |
| 10 | Subscription/billing architecture | Frontend billing UI only; no payment provider integration |

## Next recommended step

Stand up the Supabase project and apply the schema from spec section 36
(`profiles`, `subscriptions`, `assets`, `candles`, `market_features`,
`economic_events`, `models`, `model_versions`, `model_predictions`, `signals`,
`signal_results`, `backtests`, `backtest_signals`, `notification_preferences`,
`notifications`, `system_health`, `audit_logs`), wire up Supabase Auth, and swap
the frontend's demo data calls for real API/query calls one page at a time —
starting with `/dashboard` and `/dashboard/signals`, since those are the pages
every other view links back to.
