import { createClient } from "@/lib/supabase/server";
import type { NewsImpact } from "@/types";

export interface CalendarEvent {
  id: string;
  event: string;
  currency: string;
  dateTime: string; // ISO
  impact: NewsImpact;
  previous: string | null;
  forecast: string | null;
  actual: string | null;
  source: string | null;
}

/**
 * Real economic events from Supabase (spec section 25). Populated by a
 * calendar provider in apps/api -- and no real provider is configured
 * yet, so this will legitimately return [] until one is wired up.
 *
 * Important: an empty result here means "we have no calendar data", NOT
 * "nothing is scheduled". The page must say so rather than rendering a
 * clean, empty calendar that implies the day is clear.
 */
export async function getEconomicEvents(daysBack = 1, daysAhead = 7): Promise<CalendarEvent[]> {
  try {
    const supabase = await createClient();
    const now = Date.now();
    const from = new Date(now - daysBack * 86400000).toISOString();
    const to = new Date(now + daysAhead * 86400000).toISOString();

    const { data, error } = await supabase
      .from("economic_events")
      .select("id, event_name, currency, event_time, impact, previous, forecast, actual, source")
      .gte("event_time", from)
      .lte("event_time", to)
      .order("event_time", { ascending: true })
      .limit(500);

    if (error || !data) return [];

    return (data as Array<{
      id: string; event_name: string; currency: string; event_time: string;
      impact: NewsImpact; previous: string | null; forecast: string | null;
      actual: string | null; source: string | null;
    }>).map((row) => ({
      id: row.id,
      event: row.event_name,
      currency: row.currency,
      dateTime: row.event_time,
      impact: row.impact,
      previous: row.previous,
      forecast: row.forecast,
      actual: row.actual,
      source: row.source,
    }));
  } catch {
    return [];
  }
}

/**
 * Mirrors the blackout rule in apps/api/app/news/blackout.py so the UI can
 * show the same pause banner the engine acts on. Kept intentionally simple
 * (HIGH impact only, symmetric window) -- the engine remains the single
 * source of truth for whether a signal is actually suppressed; this is a
 * display of that same policy, not a second implementation of it.
 */
export const BLACKOUT_MINUTES = 30;

export function activeBlackoutEvent(events: CalendarEvent[], now = new Date()): CalendarEvent | null {
  const windowMs = BLACKOUT_MINUTES * 60000;
  const inWindow = events.filter((e) => {
    if (e.impact !== "HIGH") return false;
    const delta = new Date(e.dateTime).getTime() - now.getTime();
    return delta <= windowMs && delta >= -windowMs;
  });
  if (inWindow.length === 0) return null;
  return inWindow.reduce((nearest, e) =>
    Math.abs(new Date(e.dateTime).getTime() - now.getTime()) <
    Math.abs(new Date(nearest.dateTime).getTime() - now.getTime())
      ? e
      : nearest
  );
}
