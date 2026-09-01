-- ============================================================================
-- 20260830000017_expiry_seconds.sql
--
-- Expiries in seconds, for strategy configuration.
--
-- Migration 16 added signals.expiry_seconds. This does the same for
-- strategy_configs, which is keyed by (asset_id, expiry_minutes) and so
-- cannot currently hold a rule for a 15-SECOND horizon at all: the column is
-- minutes, and 15 seconds is not a whole number of minutes.
--
-- Broker-OTC instruments trade 15/30/60/120/180 seconds. Without this, an
-- admin can tune real-market thresholds but has no way to express a rule for
-- any OTC horizon.
--
-- BEHAVIOURAL IMPACT: none. Existing rows are backfilled from the column they
-- already have, and the loader reads expiry_seconds first with expiry_minutes
-- as the fallback, so a config written before this migration keeps applying
-- exactly as it did.
-- ============================================================================

alter table strategy_configs
  add column if not exists expiry_seconds integer
    check (expiry_seconds is null or expiry_seconds between 5 and 14400);

-- Backfill from the existing column. Safe and exact: every value stored so
-- far is a whole number of minutes by construction, because that was the only
-- thing the old column could hold.
update strategy_configs
set expiry_seconds = expiry_minutes * 60
where expiry_seconds is null and expiry_minutes is not null;

comment on column strategy_configs.expiry_seconds is
  'Authoritative horizon in seconds. expiry_minutes is the pre-OTC spelling, kept for existing rows; the loader reads seconds first so a legacy 15 (minutes) can never shadow a real 15 (seconds).';

-- expiry_minutes must become nullable: an OTC row has no whole-minute value
-- to put there, and writing a rounded one would be a four-fold lie about the
-- horizon (15 seconds is not "1 minute").
alter table strategy_configs alter column expiry_minutes drop not null;

-- The old uniqueness rule was one row per (asset, expiry_minutes). With OTC
-- rows carrying a null there, that constraint stops meaning anything --
-- Postgres treats nulls as distinct, so five OTC rows for one asset would all
-- be "unique" and silently duplicate.
--
-- Replaced with uniqueness on the seconds column, which every row has.
alter table strategy_configs
  drop constraint if exists strategy_configs_asset_id_expiry_minutes_key;

create unique index if not exists idx_strategy_configs_asset_expiry
  on strategy_configs (asset_id, expiry_seconds);

-- Every row must name its horizon in the authoritative column, or the loader
-- silently skips it and the admin's rule quietly never applies.
alter table strategy_configs
  drop constraint if exists strategy_configs_expiry_required;
alter table strategy_configs
  add constraint strategy_configs_expiry_required
  check (expiry_seconds is not null);
