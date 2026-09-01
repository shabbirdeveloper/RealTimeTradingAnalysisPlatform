import { createClient } from "@/lib/supabase/server";
import type { AssetSymbol, Direction, ExpiryMinutes, SignalGrade, SignalStatus } from "@/types";

/**
 * Real admin data -- system_health, per-asset market data status, and
 * both accepted signals and rejected opportunities (spec section 30).
 * All three tables/queries here are admin-only per RLS (system_health)
 * or rely on `is_admin()` to see REJECTED rows (signals) -- the calling
 * user's own Supabase session (via createClient()) is what grants that,
 * same as the server-side admin role check in middleware.ts.
 *
 * Every function here returns an empty array on any failure rather than
 * throwing, so an admin page can render "nothing reported yet" honestly
 * instead of crashing.
 */

export interface SystemHealthRow {
  component: string;
  status: "Healthy" | "Warning" | "Offline";
  details: Record<string, unknown>;
  lastCheckedAt: string;
}

export async function getSystemHealth(): Promise<SystemHealthRow[]> {
  try {
    const supabase = await createClient();
    const { data, error } = await supabase
      .from("system_health")
      .select("component, status, details, last_checked_at")
      .order("component", { ascending: true });
    if (error || !data) return [];
    return (data as Array<{ component: string; status: "Healthy" | "Warning" | "Offline"; details: Record<string, unknown> | null; last_checked_at: string }>).map((r) => ({
      component: r.component,
      status: r.status,
      details: r.details ?? {},
      lastCheckedAt: r.last_checked_at,
    }));
  } catch {
    return [];
  }
}

export interface AdminSignalRow {
  id: string;
  asset: AssetSymbol;
  direction: Direction;
  confidence: number | null;
  grade: SignalGrade;
  expiryMinutes: ExpiryMinutes | null;
  result: "WON" | "LOST" | "DRAW" | "PENDING";
  status: SignalStatus;
  generatedAt: string;
}

interface AdminSignalRowRaw {
  id: string;
  direction: Direction;
  generated_at: string;
  expiry_minutes: ExpiryMinutes | null;
  calibrated_confidence: number | null;
  grade: SignalGrade;
  status: SignalStatus;
  result: "WON" | "LOST" | "DRAW" | null;
  assets: { symbol: AssetSymbol } | { symbol: AssetSymbol }[] | null;
}

function shapeAdminSignalRow(row: AdminSignalRowRaw): AdminSignalRow | null {
  const assetRow = Array.isArray(row.assets) ? row.assets[0] : row.assets;
  if (!assetRow) return null;
  return {
    id: row.id,
    asset: assetRow.symbol,
    direction: row.direction,
    confidence: row.calibrated_confidence,
    grade: row.grade,
    expiryMinutes: row.expiry_minutes,
    result: row.result ?? "PENDING",
    status: row.status,
    generatedAt: row.generated_at,
  };
}

/** Everything the signal engine has generated that wasn't rejected for quality (spec section 30's "accepted signals"). */
export async function getAcceptedSignals(limit = 100): Promise<AdminSignalRow[]> {
  try {
    const supabase = await createClient();
    const { data, error } = await supabase
      .from("signals")
      .select("id, direction, generated_at, expiry_minutes, calibrated_confidence, grade, status, result, assets(symbol)")
      .neq("status", "REJECTED")
      .order("generated_at", { ascending: false })
      .limit(limit);
    if (error || !data) return [];
    return (data as unknown as AdminSignalRowRaw[]).map(shapeAdminSignalRow).filter((r): r is AdminSignalRow => r !== null);
  } catch {
    return [];
  }
}

export interface RejectedOpportunityRow {
  id: string;
  asset: AssetSymbol;
  potentialDirection: "CALL" | "PUT";
  technicalScore: number;
  reason: string;
  generatedAt: string;
}

/** Directional setups the signal engine considered but that never cleared the B-grade threshold (spec section 30's "rejected opportunities" -- admin-only via RLS). */
export async function getRejectedOpportunities(limit = 100): Promise<RejectedOpportunityRow[]> {
  try {
    const supabase = await createClient();
    const { data, error } = await supabase
      .from("signals")
      .select("id, direction, generated_at, technical_score, warnings, reasons, assets(symbol)")
      .eq("status", "REJECTED")
      .order("generated_at", { ascending: false })
      .limit(limit);
    if (error || !data) return [];
    return (data as unknown as Array<{
      id: string;
      direction: Direction;
      generated_at: string;
      technical_score: number;
      warnings: string[] | null;
      reasons: string[] | null;
      assets: { symbol: AssetSymbol } | { symbol: AssetSymbol }[] | null;
    }>).flatMap((row) => {
      const assetRow = Array.isArray(row.assets) ? row.assets[0] : row.assets;
      if (!assetRow || row.direction === "NO_TRADE") return [];
      return [{
        id: row.id,
        asset: assetRow.symbol,
        potentialDirection: row.direction as "CALL" | "PUT",
        technicalScore: row.technical_score,
        reason: (row.warnings && row.warnings[0]) ?? (row.reasons && row.reasons[0]) ?? "Below B-grade threshold.",
        generatedAt: row.generated_at,
      }];
    });
  } catch {
    return [];
  }
}

// ---------------------------------------------------------------------------
// Audit logs (spec section 38) and user list
// ---------------------------------------------------------------------------

export interface AuditLogRow {
  id: number;
  actorUserId: string | null;
  actorLabel: string;
  action: string;
  targetTable: string | null;
  targetId: string | null;
  metadata: Record<string, unknown>;
  createdAt: string;
}

/**
 * Real audit log entries. Written by apps/api (see
 * app/storage/audit_repository.py) for operational and administrative
 * events -- backtest runs, market-data failures, resolution batches.
 * Deliberately NOT a log of every signal: those are already rows in
 * `signals`, and duplicating them would bury what an operator needs to see.
 * Admin-only via RLS.
 */
export async function getAuditLogs(limit = 200): Promise<AuditLogRow[]> {
  try {
    const supabase = await createClient();
    const { data, error } = await supabase
      .from("audit_logs")
      .select("id, actor_user_id, action, target_table, target_id, metadata, created_at")
      .order("created_at", { ascending: false })
      .limit(limit);
    if (error || !data) return [];
    return (data as Array<{
      id: number; actor_user_id: string | null; action: string;
      target_table: string | null; target_id: string | null;
      metadata: Record<string, unknown> | null; created_at: string;
    }>).map((r) => ({
      id: r.id,
      actorUserId: r.actor_user_id,
      // The API service authenticates with a shared admin secret rather than
      // a user session, so most entries genuinely have no attributable user.
      actorLabel: r.actor_user_id ? "User" : "System",
      action: r.action,
      targetTable: r.target_table,
      targetId: r.target_id,
      metadata: r.metadata ?? {},
      createdAt: r.created_at,
    }));
  } catch {
    return [];
  }
}

export interface AdminUserRow {
  id: string;
  email: string | null;
  displayName: string | null;
  role: "user" | "admin";
  plan: string;
  subscriptionStatus: string | null;
  createdAt: string;
}

export type AdminUsersResult =
  | { ok: true; users: AdminUserRow[] }
  | { ok: false; error: string };

/**
 * Real user list via the `admin_list_users()` security-definer function
 * (migration 20260830000013). Emails live in `auth.users`, which the
 * browser client cannot read directly -- that function is the one hardened
 * hole, and it raises for non-admins rather than trusting the caller.
 *
 * Returns an error rather than an empty array so the page can distinguish
 * "no users" from "the function isn't installed / you aren't an admin".
 */
export async function getAdminUsers(): Promise<AdminUsersResult> {
  try {
    const supabase = await createClient();
    const { data, error } = await supabase.rpc("admin_list_users");
    if (error) return { ok: false, error: error.message };
    const users = (data ?? []) as Array<{
      id: string; email: string | null; display_name: string | null;
      role: "user" | "admin"; plan: string; subscription_status: string | null;
      created_at: string;
    }>;
    return {
      ok: true,
      users: users.map((u) => ({
        id: u.id,
        email: u.email,
        displayName: u.display_name,
        role: u.role,
        plan: u.plan,
        subscriptionStatus: u.subscription_status,
        createdAt: u.created_at,
      })),
    };
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : "Could not load users." };
  }
}

// ---------------------------------------------------------------------------
// Threshold curve — win rate by technical score, accepted vs rejected
// ---------------------------------------------------------------------------

export interface ThresholdBucket {
  label: string;
  low: number;
  accepted: { wins: number; losses: number; draws: number };
  rejected: { wins: number; losses: number; draws: number };
}

/** One curve, plus what it was computed over. */
export interface ThresholdCurveSlice {
  key: string;            // "ALL" | asset symbol | "15" | "30" | "60"
  label: string;          // what to show on the tab
  buckets: ThresholdBucket[];
  resolved: number;       // wins + losses across both columns, for sample-size honesty
}

export interface ThresholdCurveReport {
  overall: ThresholdCurveSlice;
  byAsset: ThresholdCurveSlice[];
  byExpiry: ThresholdCurveSlice[];
  /** Distinct rule sets present in the data. More than one means the numbers
   *  above pool results from different rules — see the note in the component. */
  strategyVersions: string[];
}

const BUCKETS: { label: string; low: number; high: number }[] = [
  { label: "<60", low: 0, high: 60 },
  { label: "60–69", low: 60, high: 70 },
  { label: "70–77", low: 70, high: 78 },
  { label: "78–84", low: 78, high: 85 },
  { label: "85–89", low: 85, high: 90 },
  { label: "90+", low: 90, high: 101 },
];

interface CurveRow {
  technical_score: number;
  status: string;
  result: string | null;
  shadow_result: string | null;
  expiry_minutes: number | null;
  strategy_version: string | null;
  asset_id: string;
}

function emptyBuckets(): ThresholdBucket[] {
  return BUCKETS.map((b) => ({
    label: b.label,
    low: b.low,
    accepted: { wins: 0, losses: 0, draws: 0 },
    rejected: { wins: 0, losses: 0, draws: 0 },
  }));
}

function tally(rows: CurveRow[]): { buckets: ThresholdBucket[]; resolved: number } {
  const buckets = emptyBuckets();
  let resolved = 0;

  for (const row of rows) {
    const idx = BUCKETS.findIndex((b) => row.technical_score >= b.low && row.technical_score < b.high);
    if (idx < 0) continue;
    const target = row.status === "REJECTED" ? buckets[idx].rejected : buckets[idx].accepted;
    const verdict = row.status === "REJECTED" ? row.shadow_result : row.result;
    if (verdict === "WON") { target.wins += 1; resolved += 1; }
    else if (verdict === "LOST") { target.losses += 1; resolved += 1; }
    else if (verdict === "DRAW") { target.draws += 1; }
  }
  return { buckets, resolved };
}

function slice(key: string, label: string, rows: CurveRow[]): ThresholdCurveSlice {
  const { buckets, resolved } = tally(rows);
  return { key, label, buckets, resolved };
}

function emptyReport(): ThresholdCurveReport {
  return {
    overall: { key: "ALL", label: "All", buckets: emptyBuckets(), resolved: 0 },
    byAsset: [],
    byExpiry: [],
    strategyVersions: [],
  };
}

/**
 * The curve that tells you where the quality threshold should actually sit —
 * broken down by asset and by expiry, because a single pooled curve is the
 * wrong tool for the decision it is meant to inform.
 *
 * Spec section 4 is explicit that the same parameters should not be assumed
 * to work across assets. A pooled curve hides exactly that: gold behaving
 * well and cable behaving badly average into a mediocre middle, and the one
 * threshold you set from it is wrong for both.
 *
 * `accepted` outcomes come from real resolved signals; `rejected` outcomes
 * are counterfactuals from shadow resolution — what would have happened had
 * the engine taken the setups it declined. Comparing the two is the only way
 * to know whether the threshold is doing anything: if rejected setups win at
 * the same rate as accepted ones, the filter is noise.
 *
 * Shadow outcomes live in separate columns and never touch reported accuracy.
 */
export async function getThresholdCurve(): Promise<ThresholdCurveReport> {
  try {
    const supabase = await createClient();

    const [signalsResult, assetsResult] = await Promise.all([
      supabase
        .from("signals")
        .select("technical_score, status, result, shadow_result, expiry_minutes, strategy_version, asset_id")
        .or("result.not.is.null,shadow_result.not.is.null")
        .limit(20000),
      supabase.from("assets").select("id, symbol"),
    ]);

    if (signalsResult.error || !signalsResult.data) return emptyReport();
    const rows = signalsResult.data as CurveRow[];

    const symbolById = new Map<string, string>(
      ((assetsResult.data ?? []) as { id: string; symbol: string }[]).map((a) => [a.id, a.symbol])
    );

    // Only assets that actually appear are listed. An empty tab per configured
    // asset would read as "measured, found nothing" rather than "not measured".
    const assetKeys = [...new Set(rows.map((r) => symbolById.get(r.asset_id)).filter(Boolean))] as string[];
    const byAsset = assetKeys
      .sort()
      .map((symbol) =>
        slice(symbol, symbol, rows.filter((r) => symbolById.get(r.asset_id) === symbol))
      );

    const byExpiry = [15, 30, 60]
      .map((m) => slice(String(m), `${m}m`, rows.filter((r) => r.expiry_minutes === m)))
      .filter((s) => s.resolved > 0);

    const strategyVersions = [
      ...new Set(rows.map((r) => r.strategy_version ?? "v0-unversioned")),
    ].sort();

    return {
      overall: slice("ALL", "All", rows),
      byAsset,
      byExpiry,
      strategyVersions,
    };
  } catch {
    return emptyReport();
  }
}

// ---------------------------------------------------------------------------
// Strategy configuration — what rules the engine is actually running
// ---------------------------------------------------------------------------

/** Mirrors app/features/strategy.py's shipped defaults. Kept in sync by the
 *  test in apps/api/tests/test_strategy.py, which asserts these exact values —
 *  if the engine's defaults ever change, that test fails and this constant is
 *  what has to be updated with it. */
export const STRATEGY_DEFAULTS = {
  minTechnicalScore: 78,
  regimes: ["TRENDING_UP", "TRENDING_DOWN", "RANGING", "HIGH_VOLATILITY", "LOW_VOLATILITY", "NEWS_MODE", "UNSTABLE"],
  sessions: ["ASIAN", "LONDON", "NEW_YORK", "LONDON_NY_OVERLAP"],
} as const;

export interface StrategyConfigRow {
  asset: string;
  expirySeconds: number;
  minTechnicalScore: number;
  allowedRegimes: string[];
  allowedSessions: string[];
  enabled: boolean;
  label: string;
  /** True when every field equals the shipped default, i.e. this row changes
   *  nothing. Worth stating positively rather than making the reader diff it. */
  isDefault: boolean;
  updatedAt: string | null;
}

export interface StrategyReport {
  ok: boolean;
  error?: string;
  /** Only assets with an explicit override row. Everything else runs defaults. */
  overrides: StrategyConfigRow[];
  /** Version strings actually stamped on recent signals, newest activity first.
   *  This is what the engine really applied — not what the config table says it
   *  should be. The two can disagree while a collector is between config reloads,
   *  and the stamped value is the one that describes the stored results. */
  activeVersions: { asset: string; strategyVersion: string; signals: number; lastSeen: string }[];
}

function sameSet(a: string[] | null, b: readonly string[]): boolean {
  if (!a) return true;
  return a.length === b.length && [...a].sort().join() === [...b].sort().join();
}

export async function getStrategyReport(): Promise<StrategyReport> {
  try {
    const supabase = await createClient();

    const [assetsResult, configResult, signalsResult] = await Promise.all([
      supabase.from("assets").select("id, symbol"),
      supabase
        .from("strategy_configs")
        .select("asset_id, expiry_minutes, expiry_seconds, min_technical_score, allowed_regimes, allowed_sessions, enabled, label, updated_at")
        .order("expiry_seconds", { ascending: true }),
      supabase
        .from("signals")
        .select("asset_id, strategy_version, generated_at")
        .not("strategy_version", "is", null)
        .order("generated_at", { ascending: false })
        .limit(5000),
    ]);

    if (configResult.error) {
      // Almost always "relation does not exist" — the migration hasn't been
      // applied yet. Said plainly rather than rendered as an empty table, which
      // would imply "no overrides configured" when the truth is "not readable".
      return { ok: false, error: configResult.error.message, overrides: [], activeVersions: [] };
    }

    const symbolById = new Map<string, string>(
      ((assetsResult.data ?? []) as { id: string; symbol: string }[]).map((a) => [a.id, a.symbol])
    );

    const overrides: StrategyConfigRow[] = (
      (configResult.data ?? []) as Array<{
        asset_id: string; expiry_minutes: number | null; expiry_seconds: number | null; min_technical_score: number;
        allowed_regimes: string[] | null; allowed_sessions: string[] | null;
        enabled: boolean; label: string; updated_at: string | null;
      }>
    ).map((r) => ({
      asset: symbolById.get(r.asset_id) ?? "—",
      expirySeconds: r.expiry_seconds ?? (r.expiry_minutes != null ? r.expiry_minutes * 60 : 0),
      minTechnicalScore: r.min_technical_score,
      allowedRegimes: r.allowed_regimes ?? [...STRATEGY_DEFAULTS.regimes],
      allowedSessions: r.allowed_sessions ?? [...STRATEGY_DEFAULTS.sessions],
      enabled: r.enabled,
      label: r.label,
      isDefault:
        r.enabled &&
        r.min_technical_score === STRATEGY_DEFAULTS.minTechnicalScore &&
        sameSet(r.allowed_regimes, STRATEGY_DEFAULTS.regimes) &&
        sameSet(r.allowed_sessions, STRATEGY_DEFAULTS.sessions),
      updatedAt: r.updated_at,
    }));

    const seen = new Map<string, { asset: string; strategyVersion: string; signals: number; lastSeen: string }>();
    for (const row of (signalsResult.data ?? []) as Array<{
      asset_id: string; strategy_version: string; generated_at: string;
    }>) {
      const asset = symbolById.get(row.asset_id) ?? "—";
      const key = `${asset}|${row.strategy_version}`;
      const existing = seen.get(key);
      if (existing) existing.signals += 1;
      // Rows arrive newest-first, so the first sighting is the latest.
      else seen.set(key, { asset, strategyVersion: row.strategy_version, signals: 1, lastSeen: row.generated_at });
    }

    return {
      ok: true,
      overrides,
      activeVersions: [...seen.values()].sort(
        (a, b) => a.asset.localeCompare(b.asset) || b.lastSeen.localeCompare(a.lastSeen)
      ),
    };
  } catch (err) {
    return {
      ok: false,
      error: err instanceof Error ? err.message : "Could not load strategy configuration.",
      overrides: [],
      activeVersions: [],
    };
  }
}
