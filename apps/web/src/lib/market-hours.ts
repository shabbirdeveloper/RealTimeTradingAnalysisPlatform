import type { AssetSymbol } from "@/types";
import { tradesAroundTheClock } from "@/data/assets";

/**
 * Whether an instrument's market is open, mirroring
 * apps/api/app/collector/market_hours.py.
 *
 * The collector already knew this and stopped polling closed markets; the
 * web app did not, so on a Saturday the forex cards showed a Friday close
 * with a STALE pill and no explanation. "Stale" and "closed" look identical
 * to a visitor but mean opposite things — one is a broken feed, the other is
 * the market working normally — and conflating them is the same class of
 * mistake as a catch-all that maps every failure onto one empty value.
 *
 * Deliberately duplicated rather than fetched from the API: this decides how
 * to LABEL a card, so it must resolve during render and must never leave the
 * page unable to say anything because a request failed. The two copies are
 * small, and the Python one stays authoritative for whether polling happens.
 */

/** Forex/gold: roughly Sunday 21:00 UTC through Friday 22:00 UTC. */
const OPEN_HOUR_UTC = 21; // Sunday
const CLOSE_HOUR_UTC = 22; // Friday

export function isMarketOpen(asset: AssetSymbol, now: Date = new Date()): boolean {
  // Crypto (the market never shuts) and broker-synthetics (the generator
  // never stops). Different reasons, same schedule.
  if (tradesAroundTheClock(asset)) return true;

  const day = now.getUTCDay(); // Sunday=0 ... Saturday=6
  const hour = now.getUTCHours();

  if (day === 6) return false; // Saturday
  if (day === 0 && hour < OPEN_HOUR_UTC) return false; // Sunday before the open
  if (day === 5 && hour >= CLOSE_HOUR_UTC) return false; // Friday after the close
  return true;
}

/** The next Sunday 21:00 UTC at or after `now`. Null when already open. */
export function nextOpen(asset: AssetSymbol, now: Date = new Date()): Date | null {
  if (isMarketOpen(asset, now)) return null;

  const open = new Date(now);
  open.setUTCHours(OPEN_HOUR_UTC, 0, 0, 0);
  // Walk forward to the first Sunday whose 21:00 has not already passed.
  while (open.getUTCDay() !== 0 || open.getTime() <= now.getTime()) {
    open.setUTCDate(open.getUTCDate() + 1);
    open.setUTCHours(OPEN_HOUR_UTC, 0, 0, 0);
  }
  return open;
}

/** "23h 40m" / "48m". Null when the market is open. */
export function timeUntilOpen(asset: AssetSymbol, now: Date = new Date()): string | null {
  const open = nextOpen(asset, now);
  if (!open) return null;

  const totalMinutes = Math.max(0, Math.round((open.getTime() - now.getTime()) / 60000));
  const hours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;
  return hours > 0 ? `${hours}h ${minutes}m` : `${minutes}m`;
}
