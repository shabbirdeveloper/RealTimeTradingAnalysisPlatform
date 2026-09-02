-- ============================================================================
-- 20260903000023_dashboard_performance.sql
--
-- The dashboard was making about twenty database round trips per page
-- load, several of them unindexed, and one of them pulling five thousand
-- rows to compute four numbers. Every one is a network hop from Vercel to
-- Supabase, so the page cost seconds rather than milliseconds.
--
-- Three fixes, in order of how much each was costing.
--
-- 1. A MISSING INDEX I INTRODUCED
--
-- getLatestSignals() was changed to order by last_evaluated_at (so a
-- standing decision sorts by when it was re-confirmed, not when it was
-- first reached). There is no index on that column, so each of the five
-- per-asset queries sorted every signal row for that asset. The existing
-- idx_signals_asset_generated covers generated_at only -- changing the
-- ORDER BY silently orphaned it.
--
-- 2. ELEVEN QUERIES FOR FIVE PRICES
--
-- Two queries per asset (newest candle, oldest candle) plus one for the
-- asset list. dashboard_prices() returns the same information in one
-- round trip using DISTINCT ON, which the (asset_id, timeframe,
-- open_time desc) index already serves.
--
-- 3. FIVE THOUSAND ROWS TO COUNT FOUR THINGS
--
-- getRealPerformanceSummary() selected up to 5,000 resolved signals with
-- a join and counted them in JavaScript. performance_counts() does it in
-- SQL and returns one row.
--
-- Both functions are SECURITY DEFINER, so both re-check is_approved()
-- themselves. A definer function bypasses row-level security, and one
-- that skipped that check would be a hole straight through the approval
-- gate -- exactly the kind of shortcut that makes "just add an RPC" a
-- security regression instead of a speedup.
-- ============================================================================

create index if not exists idx_signals_asset_evaluated
  on signals (asset_id, last_evaluated_at desc nulls last);

-- ---------------------------------------------------------------------------
-- One row per active asset: newest close and time, plus the oldest close
-- still stored (the baseline the change percentage is measured against).
-- ---------------------------------------------------------------------------
create or replace function dashboard_prices()
returns table (
  symbol       text,
  latest_close numeric,
  latest_time  timestamptz,
  oldest_close numeric
)
language plpgsql
security definer
set search_path = public, auth
stable
as $$
begin
  if not public.is_approved() then
    return;  -- empty, exactly as the row-level policy would have done
  end if;

  return query
  with newest as (
    select distinct on (c.asset_id) c.asset_id, c.close, c.open_time
    from candles c
    where c.timeframe = 'M5'
    order by c.asset_id, c.open_time desc
  ),
  oldest as (
    select distinct on (c.asset_id) c.asset_id, c.close
    from candles c
    where c.timeframe = 'M5'
    order by c.asset_id, c.open_time asc
  )
  select a.symbol, n.close, n.open_time, o.close
  from assets a
  join newest n on n.asset_id = a.id
  left join oldest o on o.asset_id = a.id
  where a.is_active;
end;
$$;

revoke all on function dashboard_prices() from public;
revoke all on function dashboard_prices() from anon;
grant execute on function dashboard_prices() to authenticated;

comment on function dashboard_prices() is
  'Latest and oldest stored M5 close per active asset, in one round trip. Re-checks is_approved() because SECURITY DEFINER bypasses RLS.';

-- ---------------------------------------------------------------------------
-- Resolved-signal counts, aggregated in the database.
-- ---------------------------------------------------------------------------
create or replace function performance_counts()
returns table (
  wins          bigint,
  losses        bigint,
  draws         bigint,
  aplusplus_wins   bigint,
  aplusplus_decided bigint
)
language plpgsql
security definer
set search_path = public, auth
stable
as $$
begin
  if not public.is_approved() then
    return;
  end if;

  return query
  select
    count(*) filter (where result = 'WON'),
    count(*) filter (where result = 'LOST'),
    count(*) filter (where result = 'DRAW'),
    count(*) filter (where result = 'WON'  and grade = 'A++'),
    count(*) filter (where result <> 'DRAW' and grade = 'A++')
  from signals
  where status in ('WON', 'LOST', 'DRAW');
end;
$$;

revoke all on function performance_counts() from public;
revoke all on function performance_counts() from anon;
grant execute on function performance_counts() to authenticated;

comment on function performance_counts() is
  'Resolved-signal tallies computed in SQL rather than by fetching rows. Re-checks is_approved().';
