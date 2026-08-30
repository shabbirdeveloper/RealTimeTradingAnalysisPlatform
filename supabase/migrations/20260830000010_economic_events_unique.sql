-- ============================================================================
-- 20260830000010_economic_events_unique.sql
--
-- A calendar provider re-fetches the same window repeatedly (an event's
-- `actual` value only appears after the release, so the same row must be
-- updated in place). Without a uniqueness key there is nothing to upsert
-- on and every refresh would duplicate the calendar.
--
-- Key is (event_name, currency, event_time): the same release, for the
-- same currency, at the same instant, is the same event regardless of
-- which provider reported it.
-- ============================================================================

-- Collapse any duplicates that already exist before adding the constraint,
-- keeping the most recently updated row for each key.
delete from economic_events a
using economic_events b
where a.event_name = b.event_name
  and a.currency = b.currency
  and a.event_time = b.event_time
  and (a.updated_at, a.id) < (b.updated_at, b.id);

alter table economic_events
  add constraint economic_events_natural_key
  unique (event_name, currency, event_time);
