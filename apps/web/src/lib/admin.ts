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
