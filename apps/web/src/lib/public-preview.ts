import { createClient } from "@/lib/supabase/server";
import type { AssetSymbol } from "@/types";

/**
 * The landing page's view of the engine.
 *
 * Reads through two security-definer functions (migration 20) rather than
 * the tables. The marketing site is anonymous and `signals` is gated on
 * authenticated-and-approved, so the alternatives were: open a public
 * policy and undo the approval gate, ship the service-role key to the
 * browser, or invent example signals. Those functions expose exactly the
 * shape of a decision and withhold what is tradeable.
 */

export interface PreviewRow {
  symbol: AssetSymbol;
  displayName: string;
  hasSignal: boolean;
  /** Null when a live signal exists — that is the part behind the login. */
  direction: "NO_TRADE" | null;
  grade: string | null;
  technicalScore: number | null;
  callScore: number | null;
  putScore: number | null;
  marketRegime: string | null;
  session: string | null;
  expirySeconds: number | null;
  lastEvaluatedAt: string | null;
}

export async function getPublicPreview(): Promise<PreviewRow[]> {
  try {
    const supabase = await createClient();
    const { data, error } = await supabase.rpc("public_signal_preview");
    if (error || !data) return [];
    return (data as Array<Record<string, unknown>>).map((r) => ({
      symbol: r.symbol as AssetSymbol,
      displayName: (r.display_name as string) ?? (r.symbol as string),
      hasSignal: Boolean(r.has_signal),
      direction: (r.direction as "NO_TRADE" | null) ?? null,
      grade: (r.grade as string) ?? null,
      technicalScore: r.technical_score === null ? null : Number(r.technical_score),
      callScore: r.call_score === null ? null : Number(r.call_score),
      putScore: r.put_score === null ? null : Number(r.put_score),
      marketRegime: (r.market_regime as string) ?? null,
      session: (r.session as string) ?? null,
      expirySeconds: r.expiry_seconds === null ? null : Number(r.expiry_seconds),
      lastEvaluatedAt: (r.last_evaluated_at as string) ?? null,
    }));
  } catch {
    return [];
  }
}

export interface PublicPerformance {
  /**
   * False when the query itself failed — most often because migration 20
   * has not been run yet. Without this, "0 resolved" means both "nothing
   * has expired" and "this page cannot read anything", which are opposite
   * problems that need opposite responses.
   */
  available: boolean;
  wins: number;
  losses: number;
  draws: number;
  signalsTotal: number;
  resolved: number;
  /** Null until there is enough to say anything. Never a bare number. */
  accuracy: number | null;
  interval: { low: number; high: number } | null;
  breakEven: number;
  verdict: "TOO_EARLY" | "BELOW_BREAK_EVEN" | "UNPROVEN" | "ABOVE_BREAK_EVEN";
}

/** Break-even at a typical 80% binary payout. A win rate under this loses
 *  money however impressive it looks next to 50%. */
export const BREAK_EVEN = 100 / 1.8;

/** Below this many resolved trades a rate is noise, and printing one
 *  invites a decision nobody should make on that evidence. */
export const MIN_RESOLVED = 30;

function wilson(wins: number, total: number): { low: number; high: number } {
  const z = 1.96;
  const p = wins / total;
  const d = 1 + (z * z) / total;
  const centre = (p + (z * z) / (2 * total)) / d;
  const margin =
    (z * Math.sqrt((p * (1 - p)) / total + (z * z) / (4 * total * total))) / d;
  return {
    low: Math.max(0, (centre - margin) * 100),
    high: Math.min(100, (centre + margin) * 100),
  };
}

export async function getPublicPerformance(): Promise<PublicPerformance> {
  const unavailable: PublicPerformance = {
    available: false,
    wins: 0, losses: 0, draws: 0, signalsTotal: 0, resolved: 0,
    accuracy: null, interval: null, breakEven: BREAK_EVEN, verdict: "TOO_EARLY",
  };

  try {
    const supabase = await createClient();
    const { data, error } = await supabase.rpc("public_performance");
    if (error || !data) return unavailable;

    const row = (data as Array<Record<string, unknown>>)[0];
    if (!row) return unavailable;

    const wins = Number(row.wins ?? 0);
    const losses = Number(row.losses ?? 0);
    const resolved = wins + losses;

    if (resolved < MIN_RESOLVED) {
      return {
        ...unavailable,
        available: true,
        wins, losses,
        draws: Number(row.draws ?? 0),
        signalsTotal: Number(row.signals_total ?? 0),
        resolved,
        verdict: "TOO_EARLY",
      };
    }

    const accuracy = Math.round((wins / resolved) * 1000) / 10;
    const interval = wilson(wins, resolved);

    // The verdict reads the LOWER bound, never the point estimate. A 57%
    // rate on 40 trades whose interval reaches down to 42% has not shown
    // anything, and saying otherwise is how a platform ends up claiming a
    // number it cannot defend.
    const verdict =
      interval.low > BREAK_EVEN ? "ABOVE_BREAK_EVEN"
      : interval.high < BREAK_EVEN ? "BELOW_BREAK_EVEN"
      : "UNPROVEN";

    return {
      available: true,
      wins, losses,
      draws: Number(row.draws ?? 0),
      signalsTotal: Number(row.signals_total ?? 0),
      resolved, accuracy, interval,
      breakEven: BREAK_EVEN,
      verdict,
    };
  } catch {
    return unavailable;
  }
}
