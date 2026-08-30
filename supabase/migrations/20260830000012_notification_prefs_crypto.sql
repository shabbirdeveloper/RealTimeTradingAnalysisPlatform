-- ============================================================================
-- 20260830000012_notification_prefs_crypto.sql
--
-- notification_preferences has one boolean per asset, and BTCUSD/ETHUSD were
-- added after that table was written (migration 20260830000011). Without
-- these columns the settings page could not offer alerts for the only two
-- assets that trade at the weekend -- exactly when a trader is most likely
-- to be away from the screen.
--
-- Defaults to true to match the existing per-asset columns.
-- ============================================================================

alter table notification_preferences
  add column if not exists btcusd_enabled boolean not null default true,
  add column if not exists ethusd_enabled boolean not null default true,
  -- B-grade alerts. Without this the notification feature is dead code
  -- today: the engine caps grades at B until a calibrated ML model exists
  -- (spec section 10), so A++/A+ toggles alone could never fire. Defaults
  -- to FALSE -- opt-in, because a B is explicitly not a high-conviction
  -- setup and alerting on it by default would train the user to ignore
  -- alerts.
  add column if not exists bgrade_enabled boolean not null default false;

comment on table notification_preferences is
  'One row per user. Per-asset booleans must be kept in step with the assets table — see migration 20260830000012.';
