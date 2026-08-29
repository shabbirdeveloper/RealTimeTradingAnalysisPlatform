import { createClient } from "@/lib/supabase/server";
import type { PerformanceBucket } from "@/types";

export interface BacktestRow {
  id: string;
  assetSymbol: string | null;
  expiryMinutes: number | null;
  startDate: string;
  endDate: string;
  minTechnicalScore: number | null;
  sessionFilter: string | null;
  regimeFilter: string | null;
  status: "PENDING" | "RUNNING" | "COMPLETED" | "FAILED";
  totalOpportunities: number | null;
  acceptedSignals: number | null;
  rejectedSignals: number | null;
  wins: number | null;
  losses: number | null;
  draws: number | null;
  winRate: number | null;
  accuracy: number | null;
  signalCoverage: number | null;
  maxWinStreak: number | null;
  maxLossStreak: number | null;
  byPair: PerformanceBucket[];
  byExpiry: PerformanceBucket[];
  bySession: PerformanceBucket[];
  byRegime: PerformanceBucket[];
  byScoreBucket: PerformanceBucket[];
  /** Caveats on a COMPLETED run, or the failure reason on a FAILED one. */
  message: string | null;
  createdAt: string;
  completedAt: string | null;
}

interface BacktestRowRaw {
  id: string;
  expiry_minutes: number | null;
  start_date: string;
  end_date: string;
  min_confidence: number | null;
  session_filter: string | null;
  regime_filter: string | null;
  status: BacktestRow["status"];
  total_opportunities: number | null;
  accepted_signals: number | null;
  rejected_signals: number | null;
  wins: number | null;
  losses: number | null;
  draws: number | null;
  win_rate: number | null;
  accuracy: number | null;
  signal_coverage: number | null;
  max_win_streak: number | null;
  max_loss_streak: number | null;
  performance_by_pair: PerformanceBucket[] | null;
  performance_by_expiry: PerformanceBucket[] | null;
  performance_by_session: PerformanceBucket[] | null;
  performance_by_regime: PerformanceBucket[] | null;
  performance_by_confidence_bucket: PerformanceBucket[] | null;
  error_message: string | null;
  created_at: string;
  completed_at: string | null;
  assets: { symbol: string } | { symbol: string }[] | null;
}

function shape(row: BacktestRowRaw): BacktestRow {
  const assetRow = Array.isArray(row.assets) ? row.assets[0] : row.assets;
  return {
    id: row.id,
    assetSymbol: assetRow?.symbol ?? null,
    expiryMinutes: row.expiry_minutes,
    startDate: row.start_date,
    endDate: row.end_date,
    // Stored in the schema's `min_confidence` column, but it holds a
    // technical-score threshold -- there is no calibrated model confidence
    // to threshold on yet (Phase 6). Named for what it actually is here.
    minTechnicalScore: row.min_confidence,
    sessionFilter: row.session_filter,
    regimeFilter: row.regime_filter,
    status: row.status,
    totalOpportunities: row.total_opportunities,
    acceptedSignals: row.accepted_signals,
    rejectedSignals: row.rejected_signals,
    wins: row.wins,
    losses: row.losses,
    draws: row.draws,
    winRate: row.win_rate,
    accuracy: row.accuracy,
    signalCoverage: row.signal_coverage,
    maxWinStreak: row.max_win_streak,
    maxLossStreak: row.max_loss_streak,
    byPair: row.performance_by_pair ?? [],
    byExpiry: row.performance_by_expiry ?? [],
    bySession: row.performance_by_session ?? [],
    byRegime: row.performance_by_regime ?? [],
    byScoreBucket: row.performance_by_confidence_bucket ?? [],
    message: row.error_message,
    createdAt: row.created_at,
    completedAt: row.completed_at,
  };
}

const SELECT =
  "id, expiry_minutes, start_date, end_date, min_confidence, session_filter, regime_filter, status, " +
  "total_opportunities, accepted_signals, rejected_signals, wins, losses, draws, win_rate, accuracy, " +
  "signal_coverage, max_win_streak, max_loss_streak, performance_by_pair, performance_by_expiry, " +
  "performance_by_session, performance_by_regime, performance_by_confidence_bucket, error_message, " +
  "created_at, completed_at, assets(symbol)";

/**
 * Real backtest runs from the `backtests` table (admin-only via RLS).
 * Runs are created and executed by apps/api (POST /admin/backtests) --
 * this reads results only. Returns [] on any failure so the page renders
 * an honest empty state rather than crashing.
 */
export async function getBacktests(limit = 25): Promise<BacktestRow[]> {
  try {
    const supabase = await createClient();
    const { data, error } = await supabase
      .from("backtests")
      .select(SELECT)
      .order("created_at", { ascending: false })
      .limit(limit);
    if (error || !data) return [];
    return (data as unknown as BacktestRowRaw[]).map(shape);
  } catch {
    return [];
  }
}
