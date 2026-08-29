-- ============================================================================
-- 20260829000001_extensions_and_enums.sql
--
-- Extensions and shared enum types for the NorthFXTrade schema (spec section
-- 36). All timestamps in this schema are stored as `timestamptz` and written
-- in UTC by the application layer — never rely on the database session's
-- local timezone.
-- ============================================================================

create extension if not exists "pgcrypto";      -- gen_random_uuid()

-- Direction a signal (or a rejected opportunity) points.
create type direction_type as enum ('CALL', 'PUT', 'NO_TRADE');

-- Signal quality tier. REJECTED means it never cleared the B threshold.
create type signal_grade as enum ('A++', 'A+', 'A', 'B', 'REJECTED');

-- Lifecycle status of a signal row (spec section 37).
create type signal_status as enum (
  'CANDIDATE', 'REJECTED', 'ACTIVE', 'EXPIRED',
  'WON', 'LOST', 'DRAW', 'INVALIDATED'
);

-- Market regime classification (spec section 7).
create type market_regime_type as enum (
  'TRENDING_UP', 'TRENDING_DOWN', 'RANGING',
  'HIGH_VOLATILITY', 'LOW_VOLATILITY', 'NEWS_MODE', 'UNSTABLE'
);

-- Candle / analysis timeframe.
create type timeframe_type as enum ('M5', 'M15', 'H1', 'H4');

-- Market data freshness (spec section 42).
create type data_status_type as enum ('LIVE', 'DELAYED', 'STALE', 'OFFLINE');

-- ML model lifecycle (spec section 31). Nothing here means "deployed
-- automatically" — ACTIVE is a deliberate, explicit transition.
create type model_status_type as enum (
  'TRAINING', 'VALIDATING', 'READY', 'ACTIVE', 'ARCHIVED', 'FAILED'
);

-- Economic-calendar event impact (spec section 25).
create type event_impact_type as enum ('LOW', 'MEDIUM', 'HIGH');

-- Platform role. Admin routes are gated on this (spec section 28/38) —
-- server-side, RLS is not the only check; see the note in the RLS migration.
create type user_role as enum ('user', 'admin');

-- Backtest job lifecycle (spec section 13/32).
create type backtest_status as enum ('PENDING', 'RUNNING', 'COMPLETED', 'FAILED');

-- Health status for a monitored system component (spec section 29/35).
create type component_status as enum ('Healthy', 'Warning', 'Offline');
