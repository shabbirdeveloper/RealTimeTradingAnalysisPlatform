import { createClient } from "@/lib/supabase/server";

/**
 * What the 5-minute OTC engine is actually doing, cycle by cycle.
 *
 * The engine declines most of the time by design, and a page that shows
 * only accepted signals therefore shows almost nothing — which reads as a
 * dead system rather than a selective one. That misreading is expensive:
 * the natural response to "my dashboard never changes" is to distrust it
 * or to lower the quality bar until it speaks, and the second is how a
 * signal platform ends up losing money confidently.
 *
 * So this reads REJECTED decisions too. Every evaluation is stored with
 * the gate that stopped it, and that record is the product's real output.
 *
 * RLS note: migration 18 hides CANDIDATE and REJECTED rows from
 * non-admins. A non-admin therefore sees the accepted signals and an
 * honest note that the rejections are admin-only — never an empty page
 * implying nothing happened.
 */

export interface EngineDecision {
  id: string;
  symbol: string;
  generatedAt: string;
  direction: string;
  status: string;
  callScore: number | null;
  putScore: number | null;
  technicalScore: number | null;
  regime: string | null;
  regimeReason: string | null;
  strategy: string | null;
  feedStatus: string | null;
  entryPrice: number | null;
  expirySeconds: number | null;
  expiryAt: string | null;
  result: string | null;
  closingPrice: number | null;
  rejectionReasons: string[];
  reasons: string[];
  warnings: string[];
  callCategories: Record<string, number> | null;
  putCategories: Record<string, number> | null;
}

export interface EngineSnapshot {
  /** False when the query itself failed — distinct from "nothing yet". */
  available: boolean;
  error: string | null;
  /** True when REJECTED rows are invisible to this reader (not an admin). */
  rejectionsHidden: boolean;
  latest: EngineDecision | null;
  recent: EngineDecision[];
  today: {
    evaluations: number;
    signals: number;
    rejections: number;
    won: number;
    lost: number;
    draw: number;
    pending: number;
  };
  /** Which gate stopped the most cycles today, most frequent first. */
  topBlockers: Array<{ reason: string; count: number }>;
}

const EMPTY_TODAY = {
  evaluations: 0, signals: 0, rejections: 0,
  won: 0, lost: 0, draw: 0, pending: 0,
};

/** Reasons differ in their numbers ("score 63 below the 78 floor"). Group
 *  by the SHAPE of the reason, or every cycle looks like a unique problem
 *  and the ranking says nothing. */
function normaliseReason(reason: string): string {
  return reason
    .replace(/\d+(\.\d+)?/g, "N")
    .replace(/\s+/g, " ")
    .trim();
}

function shape(raw: Record<string, unknown>): EngineDecision {
  const snap = (raw.timeframes_snapshot ?? {}) as Record<string, unknown>;
  const assets = raw.assets as { symbol?: string } | { symbol?: string }[] | undefined;
  const asset = Array.isArray(assets) ? assets[0] : assets;
  return {
    id: String(raw.id),
    symbol: asset?.symbol ?? "—",
    generatedAt: String(raw.generated_at),
    direction: String(raw.direction ?? "NO_TRADE"),
    status: String(raw.status ?? ""),
    callScore: raw.call_score === null || raw.call_score === undefined ? null : Number(raw.call_score),
    putScore: raw.put_score === null || raw.put_score === undefined ? null : Number(raw.put_score),
    technicalScore: raw.technical_score === null || raw.technical_score === undefined ? null : Number(raw.technical_score),
    regime: (raw.market_regime as string) ?? null,
    regimeReason: (snap.regime_reason as string) ?? null,
    strategy: (snap.strategy as string) ?? null,
    feedStatus: (snap.feed_status as string) ?? null,
    entryPrice: raw.entry_price === null || raw.entry_price === undefined ? null : Number(raw.entry_price),
    expirySeconds: raw.expiry_seconds === null || raw.expiry_seconds === undefined ? null : Number(raw.expiry_seconds),
    expiryAt: (raw.expiry_at as string) ?? null,
    result: (raw.result as string) ?? null,
    closingPrice: raw.closing_price === null || raw.closing_price === undefined ? null : Number(raw.closing_price),
    rejectionReasons: (snap.rejection_reasons as string[]) ?? [],
    reasons: (raw.reasons as string[]) ?? [],
    warnings: (raw.warnings as string[]) ?? [],
    callCategories: (snap.call_categories as Record<string, number>) ?? null,
    putCategories: (snap.put_categories as Record<string, number>) ?? null,
  };
}

const COLUMNS =
  "id, direction, status, generated_at, entry_price, expiry_seconds, expiry_at, " +
  "technical_score, call_score, put_score, market_regime, result, closing_price, " +
  "reasons, warnings, timeframes_snapshot, assets!inner(symbol)";

export async function getEngineSnapshot(limit = 40): Promise<EngineSnapshot> {
  const base: EngineSnapshot = {
    available: false, error: null, rejectionsHidden: false,
    latest: null, recent: [], today: { ...EMPTY_TODAY }, topBlockers: [],
  };

  let supabase;
  try {
    supabase = await createClient();
  } catch (e) {
    return { ...base, error: e instanceof Error ? e.message : "Supabase is not configured." };
  }

  const midnight = new Date();
  midnight.setUTCHours(0, 0, 0, 0);

  const { data, error } = await supabase
    .from("signals")
    .select(COLUMNS)
    .eq("market_type", "BROKER_OTC")
    .gte("generated_at", midnight.toISOString())
    .order("generated_at", { ascending: false })
    .limit(600);

  if (error) return { ...base, error: error.message };

  const rows = ((data ?? []) as Array<Record<string, unknown>>).map(shape);

  // No rows today is a real, ordinary answer — the engine may have been
  // started minutes ago. It is reported as available-with-nothing rather
  // than as an error, because those need different responses.
  const today = { ...EMPTY_TODAY, evaluations: rows.length };
  const blockers = new Map<string, number>();

  for (const row of rows) {
    if (row.status === "REJECTED" || row.status === "CANDIDATE") {
      today.rejections += 1;
      for (const reason of row.rejectionReasons.slice(0, 1)) {
        const key = normaliseReason(reason);
        blockers.set(key, (blockers.get(key) ?? 0) + 1);
      }
      continue;
    }
    today.signals += 1;
    if (row.status === "WON") today.won += 1;
    else if (row.status === "LOST") today.lost += 1;
    else if (row.status === "DRAW") today.draw += 1;
    else if (row.status === "ACTIVE") today.pending += 1;
  }

  return {
    ...base,
    available: true,
    // RLS filters rejections out entirely for non-admins. Evaluations with
    // zero rejections and at least one row means the reader is seeing a
    // filtered view, not a market that never declined.
    rejectionsHidden: rows.length > 0 && today.rejections === 0 && today.signals === rows.length,
    latest: rows[0] ?? null,
    recent: rows.slice(0, limit),
    today,
    topBlockers: [...blockers.entries()]
      .map(([reason, count]) => ({ reason, count }))
      .sort((a, b) => b.count - a.count)
      .slice(0, 6),
  };
}
