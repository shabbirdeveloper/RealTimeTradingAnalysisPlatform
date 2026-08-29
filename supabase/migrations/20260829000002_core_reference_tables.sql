-- ============================================================================
-- 20260829000002_core_reference_tables.sql
--
-- profiles, subscriptions, assets, economic_events.
-- ============================================================================

create type subscription_status as enum (
  'trialing', 'active', 'past_due', 'canceled', 'incomplete'
);

-- One row per authenticated user, 1:1 with auth.users. Created by a trigger
-- (see bottom of this file) so every signup gets a profile automatically.
create table profiles (
  id            uuid primary key references auth.users (id) on delete cascade,
  display_name  text,
  role          user_role not null default 'user',
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now()
);

comment on table profiles is 'One row per authenticated user. role=admin gates /admin routes (checked server-side, not by RLS alone).';

-- Billing state. UI-only today (spec section 10/50) — no payment provider is
-- wired up yet, so this table exists for the schema/shape but stays empty
-- until a real provider (Stripe et al.) is integrated in Phase 10.
create table subscriptions (
  id                     uuid primary key default gen_random_uuid(),
  user_id                uuid not null references profiles (id) on delete cascade,
  plan                   text not null default 'free',
  status                 subscription_status not null default 'active',
  provider               text,                     -- e.g. 'stripe'; null until Phase 10
  provider_customer_id   text,
  provider_subscription_id text,
  current_period_end    timestamptz,
  created_at             timestamptz not null default now(),
  updated_at             timestamptz not null default now(),
  unique (user_id)
);

-- The three configured instruments. Seeded by the seed script, not by the
-- application — new pairs are added here, not hardcoded in the frontend
-- (spec: "architecture so the application can later support additional
-- pairs without major refactoring").
create table assets (
  id            uuid primary key default gen_random_uuid(),
  symbol        text not null unique,       -- 'XAUUSD' | 'EURUSD' | 'GBPUSD'
  display_name  text not null,              -- 'XAU/USD'
  short_name    text not null,              -- 'Gold', 'Euro', 'Cable'
  pip_decimal   smallint not null,
  config        jsonb not null default '{}'::jsonb,  -- per-asset params (spec section 4): DXY weighting, session emphasis, etc.
  is_active     boolean not null default true,
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now()
);

-- Economic calendar (spec section 8/25). `actual` is null until the event
-- has occurred; the news filter reads `impact` + `event_time` to decide
-- blackout windows.
create table economic_events (
  id            uuid primary key default gen_random_uuid(),
  event_name    text not null,
  currency      text not null,              -- 'USD', 'EUR', 'GBP', ...
  event_time    timestamptz not null,
  impact        event_impact_type not null,
  previous      text,
  forecast      text,
  actual        text,
  source        text,                       -- calendar provider name
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now()
);

create index idx_economic_events_time on economic_events (event_time);
create index idx_economic_events_currency_impact on economic_events (currency, impact);

-- Keep profiles.updated_at / subscriptions.updated_at current on write.
create or replace function set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

create trigger trg_profiles_updated_at
  before update on profiles
  for each row execute function set_updated_at();

create trigger trg_subscriptions_updated_at
  before update on subscriptions
  for each row execute function set_updated_at();

create trigger trg_assets_updated_at
  before update on assets
  for each row execute function set_updated_at();

create trigger trg_economic_events_updated_at
  before update on economic_events
  for each row execute function set_updated_at();

-- Auto-create a profile row whenever a new Supabase Auth user signs up.
create or replace function handle_new_user()
returns trigger
language plpgsql
security definer set search_path = public
as $$
begin
  insert into public.profiles (id, display_name)
  values (new.id, new.raw_user_meta_data ->> 'display_name');
  return new;
end;
$$;

create trigger trg_on_auth_user_created
  after insert on auth.users
  for each row execute function handle_new_user();
