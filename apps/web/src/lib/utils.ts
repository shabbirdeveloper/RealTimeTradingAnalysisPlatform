import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatPrice(value: number, decimals = 2): string {
  return value.toLocaleString("en-US", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

export function formatPercent(value: number, decimals = 1): string {
  return `${value.toFixed(decimals)}%`;
}

export function formatCountdown(msRemaining: number): string {
  if (msRemaining <= 0) return "00:00";
  const totalSeconds = Math.floor(msRemaining / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}

export function formatTimeUTC(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleTimeString("en-GB", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    timeZone: "UTC",
    hour12: false,
  }) + " UTC";
}

export function formatDateTimeUTC(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleString("en-GB", {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "UTC",
    hour12: false,
  }) + " UTC";
}

/**
 * Human-readable trade horizon. Mirrors format_expiry() in
 * apps/api/app/features/strategy.py — the two must agree, or the same signal
 * reads differently in the dashboard than in the engine's own reasons.
 *
 * Takes SECONDS. Real-market horizons are 15/30/60 minutes; broker-OTC
 * horizons are 15–180 seconds, and a single "N min" template cannot render
 * both — a 15-second expiry shown as "0 min" or "1 min" is not a rounding
 * error, it is the wrong trade.
 */
export function formatExpiry(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return "—";
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  const rest = seconds % 60;
  return rest === 0 ? `${minutes}m` : `${minutes}m${rest}s`;
}

/**
 * Seconds for a signal that may carry either column. `expirySeconds` is
 * authoritative; `expiryMinutes` is the pre-OTC spelling. Read in this order
 * so a legacy 15 (minutes) can never shadow a real 15 (seconds).
 */
export function expirySecondsOf(signal: {
  expirySeconds?: number | null;
  expiryMinutes?: number | null;
}): number | null {
  if (signal.expirySeconds !== null && signal.expirySeconds !== undefined) {
    return signal.expirySeconds;
  }
  return signal.expiryMinutes != null ? signal.expiryMinutes * 60 : null;
}

/**
 * "3m ago" / "2h ago" / "1d ago". Used for the engine's last-checked
 * stamp, where the question is "is this still alive?" and an absolute UTC
 * timestamp forces the reader to do the subtraction themselves -- badly,
 * across timezones, at the exact moment they are trying to decide whether
 * their money is riding on stale analysis.
 */
export function formatRelative(iso: string | null | undefined, now: number = Date.now()): string {
  if (!iso) return "unknown";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "unknown";
  const seconds = Math.max(0, Math.round((now - then) / 1000));
  if (seconds < 90) return `${seconds}s ago`;
  const minutes = Math.round(seconds / 60);
  if (minutes < 90) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 36) return `${hours}h ago`;
  return `${Math.round(hours / 24)}d ago`;
}

/**
 * Spec section 42: every market object carries a status, and stale data is
 * never shown as live.
 *
 * The engine re-evaluates a real-market asset every 300 seconds, so a
 * decision a few minutes old is current and one an hour old describes a
 * market that has moved on. A single boolean could not say which: the
 * landing page was marking a decision red for being old while still
 * rendering "Signal open" beside it, which reads as an open position a
 * visitor could act on. These four states keep "recent enough to act on",
 * "getting old", "do not act on this" and "nothing is arriving" apart.
 */
export type DataStatus = "LIVE" | "DELAYED" | "STALE" | "OFFLINE";

export function dataStatus(iso: string | null | undefined, now: number = Date.now()): DataStatus {
  if (!iso) return "OFFLINE";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "OFFLINE";
  const minutes = (now - then) / 60_000;
  if (minutes <= 10) return "LIVE";
  if (minutes <= 30) return "DELAYED";
  if (minutes <= 360) return "STALE";
  return "OFFLINE";
}

/** STALE and OFFLINE both mean: do not present this as a current decision. */
export function isActionable(status: DataStatus): boolean {
  return status === "LIVE" || status === "DELAYED";
}

/** True when the engine has not re-confirmed a decision recently. */
export function isCheckStale(iso: string | null | undefined, now: number = Date.now(), maxMinutes = 30): boolean {
  if (!iso) return true;
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return true;
  return now - then > maxMinutes * 60_000;
}
