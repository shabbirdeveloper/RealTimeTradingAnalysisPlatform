/**
 * Which collectors the backend is actually running.
 *
 * The dashboard used to tell a viewer "engine may be stopped" whenever a
 * card went stale. That was a guess dressed as a diagnosis, and it is now
 * wrong in the ordinary case: the public-market collector is deliberately
 * off while the engineering effort is concentrated on one broker-OTC
 * series, so those cards go stale BY DESIGN.
 *
 * Deliberately broken and deliberately switched off look identical from
 * the outside and call for opposite responses -- one is a page to fix at
 * 3am, the other is nothing at all. This is the same distinction as
 * stale-versus-closed on the weekend cards, and getting it wrong has cost
 * this project real hours.
 *
 * Read server-side ONLY, and deliberately WITHOUT the `server-only`
 * package: a dependency that is not in the lockfile makes Vercel's
 * `npm ci` fail outright, which is a worse failure than the one that
 * guard prevents.
 *
 * The guarantee is by construction instead: the variable carries no
 * NEXT_PUBLIC_ prefix, so Next.js never inlines it into the browser
 * bundle. A client component importing this reads `undefined` and
 * falls through to the safe default rather than leaking anything.
 *
 * Read server-side only. It mirrors the API's own
 * PUBLIC_MARKET_COLLECTOR_ENABLED, so the two must be set together --
 * there is no way for the web app to observe the scheduler directly.
 */
export function publicMarketCollectorEnabled(): boolean {
  const raw = process.env.PUBLIC_MARKET_COLLECTOR_ENABLED;
  // Default false, matching the API's default. A missing variable meaning
  // "on" would put the misleading message back the moment someone forgot
  // to set it.
  if (raw === undefined) return false;
  return raw.toLowerCase() === "true" || raw === "1";
}

/** What to say when a real-market card has not been checked in a while. */
export function staleNoteForRealMarket(): string {
  return publicMarketCollectorEnabled()
    ? "engine may be stopped"
    : "real-market collector is switched off";
}

export interface EngineHeartbeat {
  component: string;
  status: string;
  lastCheckedAt: string;
  details: Record<string, unknown>;
  ageSeconds: number;
}

/**
 * Whether the engine has actually run recently.
 *
 * "Engine may be stopped" was a GUESS, inferred from a decision being old.
 * It is wrong in both directions: an engine that runs every cycle and
 * declines every setup looks stopped, and an engine that genuinely died
 * looks merely quiet. Both readings have cost hours in this project.
 *
 * The engine now records a heartbeat every cycle, whatever the outcome —
 * including when the cycle FAILED, because "ran and declined everything"
 * and "never ran" leave the decisions table looking identical and need
 * opposite responses. This reads that row, so the page can state which
 * happened instead of inferring it.
 */
export async function getEngineHeartbeats(): Promise<EngineHeartbeat[]> {
  try {
    const { createClient } = await import("@/lib/supabase/server");
    const supabase = await createClient();
    const { data, error } = await supabase
      .from("system_health")
      .select("component, status, details, last_checked_at")
      .like("component", "Signal Engine%");

    if (error || !data) return [];

    const now = Date.now();
    return (data as Array<Record<string, unknown>>).map((r) => ({
      component: String(r.component),
      status: String(r.status),
      lastCheckedAt: String(r.last_checked_at),
      details: (r.details as Record<string, unknown>) ?? {},
      ageSeconds: Math.max(0, Math.round((now - new Date(String(r.last_checked_at)).getTime()) / 1000)),
    }));
  } catch {
    return [];
  }
}
