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

const BUCKETS: { label: string; low: number; high: number }[] = [
  { label: "<60", low: 0, high: 60 },
  { label: "60–69", low: 60, high: 70 },
  { label: "70–77", low: 70, high: 78 },
  { label: "78–84", low: 78, high: 85 },
  { label: "85–89", low: 85, high: 90 },
  { label: "90+", low: 90, high: 100 },
];

/**
 * The curve that tells you where the quality threshold should actually sit.
 *
 * `accepted` outcomes come from real resolved signals; `rejected` outcomes are
 * counterfactuals from shadow resolution — what would have happened had the
 * engine taken the setups it declined. Comparing the two is the only way to
 * know whether the threshold is doing anything: if rejected setups win at the
 * same rate as accepted ones, the filter is noise.
 *
 * Shadow outcomes live in separate columns and never touch reported accuracy.
 */
export async function getThresholdCurve(): Promise<ThresholdBucket[]> {
  const empty = () => ({ wins: 0, losses: 0, draws: 0 });
  const buckets: ThresholdBucket[] = BUCKETS.map((b) => ({
    label: b.label, low: b.low, accepted: empty(), rejected: empty(),
  }));

  try {
    const supabase = await createClient();
    const { data, error } = await supabase
      .from("signals")
      .select("technical_score, status, result, shadow_result")
      .or("result.not.is.null,shadow_result.not.is.null")
      .limit(20000);
    if (error || !data) return buckets;

    for (const row of data as Array<{
      technical_score: number; status: string;
      result: string | null; shadow_result: string | null;
    }>) {
      const idx = BUCKETS.findIndex((b) => row.technical_score >= b.low && row.technical_score < b.high);
      if (idx < 0) continue;
      const target = row.status === "REJECTED" ? buckets[idx].rejected : buckets[idx].accepted;
      const verdict = row.status === "REJECTED" ? row.shadow_result : row.result;
      if (verdict === "WON") target.wins += 1;
      else if (verdict === "LOST") target.losses += 1;
      else if (verdict === "DRAW") target.draws += 1;
    }
    return buckets;
  } catch {
    return buckets;
  }
}
