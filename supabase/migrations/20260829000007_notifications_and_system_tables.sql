-- ============================================================================
-- 20260829000007_notifications_and_system_tables.sql
--
-- notification_preferences, notifications, system_health, audit_logs.
-- ============================================================================

-- One row per user (spec section 26's settings list).
create table notification_preferences (
  user_id           uuid primary key references profiles (id) on delete cascade,
  aplusplus_enabled boolean not null default true,
  aplus_enabled     boolean not null default true,
  xauusd_enabled    boolean not null default true,
  eurusd_enabled    boolean not null default true,
  gbpusd_enabled    boolean not null default true,
  browser_enabled   boolean not null default false,
  telegram_enabled  boolean not null default false,
  telegram_chat_id  text,
  email_enabled     boolean not null default false,
  created_at        timestamptz not null default now(),
  updated_at        timestamptz not null default now()
);

create trigger trg_notification_preferences_updated_at
  before update on notification_preferences
  for each row execute function set_updated_at();

-- Auto-create default preferences alongside every new profile.
create or replace function handle_new_profile()
returns trigger
language plpgsql
security definer set search_path = public
as $$
begin
  insert into public.notification_preferences (user_id) values (new.id);
  return new;
end;
$$;

create trigger trg_on_profile_created
  after insert on profiles
  for each row execute function handle_new_profile();

create table notifications (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid not null references profiles (id) on delete cascade,
  type        text not null,             -- 'SIGNAL_APLUSPLUS' | 'SIGNAL_APLUS' | 'SYSTEM' | 'BILLING' | ...
  title       text not null,
  body        text,
  signal_id   uuid references signals (id) on delete set null,
  read_at     timestamptz,
  created_at  timestamptz not null default now()
);

create index idx_notifications_user_created on notifications (user_id, created_at desc);
create index idx_notifications_user_unread on notifications (user_id) where read_at is null;

-- Current status per monitored component (spec section 35's fixed list:
-- Frontend, API, Database, Market Data, Feature Engine, Signal Engine, ML
-- Engine, News API, Notifications, WebSockets). One row per component,
-- upserted on every health check — this is current state, not a log.
create table system_health (
  component        text primary key,
  status           component_status not null,
  details          jsonb not null default '{}'::jsonb,
  last_checked_at  timestamptz not null default now()
);

-- Every accepted AND rejected signal must be attributable, and every admin
-- action auditable (spec section 38). actor_user_id is null for
-- system/service-initiated actions (e.g. the signal engine itself).
create table audit_logs (
  id             bigint generated always as identity primary key,
  actor_user_id  uuid references profiles (id),
  action         text not null,           -- e.g. 'model.activate', 'backtest.run', 'signal.reject'
  target_table   text,
  target_id      text,
  metadata       jsonb not null default '{}'::jsonb,
  created_at     timestamptz not null default now()
);

create index idx_audit_logs_actor on audit_logs (actor_user_id);
create index idx_audit_logs_created on audit_logs (created_at desc);
