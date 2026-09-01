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
