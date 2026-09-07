import "server-only";

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
