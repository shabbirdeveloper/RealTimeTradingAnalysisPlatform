import { createClient } from "@/lib/supabase/server";
import type { AssetSymbol, PerformanceBucket, PerformanceSummary } from "@/types";

interface ResolvedSignalRow {
  asset_symbol: AssetSymbol;
  expiry_minutes: number | null;
  session: string | null;
  market_regime: string;
  technical_score: number;
  grade: string;
  result: "WON" | "LOST" | "DRAW";
  resolved_at: string;
}

function emptyBucket(label: string): PerformanceBucket {
  return { label, signals: 0, wins: 0, losses: 0, draws: 0, accuracy: 0 };
}

function accumulate(buckets: Map<string, PerformanceBucket>, key: string, result: "WON" | "LOST" | "DRAW") {
  const bucket = buckets.get(key) ?? emptyBucket(key);
  bucket.signals += 1;
  if (result === "WON") bucket.wins += 1;
  else if (result === "LOST") bucket.losses += 1;
  else bucket.draws += 1;
  const decided = bucket.wins + bucket.losses;
  bucket.accuracy = decided > 0 ? Math.round((bucket.wins / decided) * 1000) / 10 : 0;
  buckets.set(key, bucket);
}

function technicalScoreBucketLabel(score: number): string {
  if (score >= 90) return "90-99";
  if (score >= 80) return "80-89";
  if (score >= 70) return "70-79";
  if (score >= 60) return "60-69";
  return "<60";
}

/**
 * Real performance stats computed from resolved (WON/LOST/DRAW) rows in
 * `signals` -- written by apps/api's resolution job (spec section 49,
 * app/collector/resolution.py). There is no shortcut to a real accuracy
 * number here: it only exists once real signals have actually expired
 * and been checked against a real closing price, which takes real time.
 *
 * Returns null if the query fails outright (Supabase not configured,
 * etc.) so the caller can fall back to an honest empty state. An empty
 * *array* of resolved signals is NOT a failure -- it returns a valid,
 * all-zero PerformanceSummary, because "no real trades have resolved
 * yet" is itself an honest, real answer (never swapped for demo
 * numbers).
 *
 * `byConfidenceBucket` buckets by Technical Score, not calibrated ML
 * confidence -- there is no calibrated confidence yet (Phase 6), so
 * bucketing by it isn't possible without fabricating one.
 */
export async function getRealPerformanceSummary(): Promise<PerformanceSummary | null> {
  try {
    const supabase = await createClient();

    const { data, error } = await supabase
      .from("signals")
      .select(
        "expiry_minutes, session, market_regime, technical_score, grade, result, resolved_at, assets(symbol)"
      )
      .in("status", ["WON", "LOST", "DRAW"])
      .order("resolved_at", { ascending: true })
      .limit(5000);

    if (error) return null;

    const rows: ResolvedSignalRow[] = ((data ?? []) as unknown as Array<{
      expiry_minutes: number | null;
      session: string | null;
      market_regime: string;
      technical_score: number;
      grade: string;
      result: "WON" | "LOST" | "DRAW";
      resolved_at: string;
      assets: { symbol: AssetSymbol } | { symbol: AssetSymbol }[] | null;
    }>).flatMap((row) => {
      const assetRow = Array.isArray(row.assets) ? row.assets[0] : row.assets;
      if (!assetRow) return [];
      return [{ ...row, asset_symbol: assetRow.symbol }];
    });

    const wins = rows.filter((r) => r.result === "WON").length;
    const losses = rows.filter((r) => r.result === "LOST").length;
    const draws = rows.filter((r) => r.result === "DRAW").length;
    const decided = wins + losses;
    const overallAccuracy = decided > 0 ? Math.round((wins / decided) * 1000) / 10 : 0;

    const aPlusPlusRows = rows.filter((r) => r.grade === "A++");
    const aPlusPlusWins = aPlusPlusRows.filter((r) => r.result === "WON").length;
    const aPlusPlusDecided = aPlusPlusRows.filter((r) => r.result !== "DRAW").length;
    const aPlusPlusAccuracy = aPlusPlusDecided > 0 ? Math.round((aPlusPlusWins / aPlusPlusDecided) * 1000) / 10 : 0;

    // Current streak: walk backwards from the most recently resolved
    // signal, counting consecutive same-result decided (non-draw) rows.
    const decidedRows = rows.filter((r) => r.result !== "DRAW");
    let currentStreak: { type: "WIN" | "LOSS" | "NONE"; count: number } = { type: "NONE", count: 0 };
    if (decidedRows.length > 0) {
      const lastType = decidedRows[decidedRows.length - 1]!.result === "WON" ? "WIN" : "LOSS";
      let count = 0;
      for (let i = decidedRows.length - 1; i >= 0; i--) {
        const t = decidedRows[i]!.result === "WON" ? "WIN" : "LOSS";
        if (t !== lastType) break;
        count += 1;
      }
      currentStreak = { type: lastType, count };
    }

    let maxWinStreak = 0;
    let maxLossStreak = 0;
    let runType: "WIN" | "LOSS" | null = null;
    let runLength = 0;
    for (const r of decidedRows) {
      const t = r.result === "WON" ? "WIN" : "LOSS";
      if (t === runType) runLength += 1;
      else {
        runType = t;
        runLength = 1;
      }
      if (t === "WIN") maxWinStreak = Math.max(maxWinStreak, runLength);
      else maxLossStreak = Math.max(maxLossStreak, runLength);
    }

    const byAssetMap = new Map<string, PerformanceBucket>();
    const byExpiryMap = new Map<string, PerformanceBucket>();
    const bySessionMap = new Map<string, PerformanceBucket>();
    const byRegimeMap = new Map<string, PerformanceBucket>();
    const byScoreBucketMap = new Map<string, PerformanceBucket>();
    const byDay = new Map<string, { wins: number; losses: number; draws: number }>();

    for (const r of rows) {
      accumulate(byAssetMap, r.asset_symbol, r.result);
      accumulate(byExpiryMap, r.expiry_minutes ? `${r.expiry_minutes}m` : "—", r.result);
      accumulate(bySessionMap, r.session ?? "—", r.result);
      accumulate(byRegimeMap, r.market_regime, r.result);
      accumulate(byScoreBucketMap, technicalScoreBucketLabel(r.technical_score), r.result);

      const day = r.resolved_at.slice(0, 10);
      const entry = byDay.get(day) ?? { wins: 0, losses: 0, draws: 0 };
      if (r.result === "WON") entry.wins += 1;
      else if (r.result === "LOST") entry.losses += 1;
      else entry.draws += 1;
      byDay.set(day, entry);
    }

    const days = Array.from(byDay.keys()).sort();
    let cumWins = 0;
    let cumLosses = 0;
    const accuracyOverTime = days.map((date) => {
      const { wins: w, losses: l } = byDay.get(date)!;
      cumWins += w;
      cumLosses += l;
      const dayDecided = cumWins + cumLosses;
      return {
        date,
        accuracy: dayDecided > 0 ? Math.round((cumWins / dayDecided) * 1000) / 10 : 0,
        signals: dayDecided,
      };
    });
    let runningWins = 0;
    let runningLosses = 0;
    const cumulative = days.map((date) => {
      const { wins: w, losses: l } = byDay.get(date)!;
      runningWins += w;
      runningLosses += l;
      return { date, wins: runningWins, losses: runningLosses };
    });

    return {
      totalSignals: rows.length,
      wins,
      losses,
      draws,
      overallAccuracy,
      aPlusPlusSignals: aPlusPlusRows.length,
      aPlusPlusAccuracy,
      currentStreak,
      maxWinStreak,
      maxLossStreak,
      byAsset: Array.from(byAssetMap.values()),
      byExpiry: Array.from(byExpiryMap.values()),
      bySession: Array.from(bySessionMap.values()),
      byRegime: Array.from(byRegimeMap.values()),
      byConfidenceBucket: Array.from(byScoreBucketMap.values()),
      accuracyOverTime,
      cumulative,
    };
  } catch {
    return null;
  }
}
