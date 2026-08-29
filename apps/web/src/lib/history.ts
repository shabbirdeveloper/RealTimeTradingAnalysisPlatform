import { createClient } from "@/lib/supabase/server";
import type { AssetSymbol, Direction, ExpiryMinutes, SignalGrade, SignalStatus } from "@/types";

export interface HistoryRow {
  id: string;
  asset: AssetSymbol;
  direction: Direction;
  confidence: number | null;
  grade: SignalGrade;
  expiryMinutes: ExpiryMinutes | null;
  entryPrice: number | null;
  closingPrice: number | null;
  result: "WON" | "LOST" | "DRAW" | "PENDING";
  status: SignalStatus;
  generatedAt: string;
}

interface HistoryRowRaw {
  id: string;
  direction: Direction;
  generated_at: string;
  entry_price: string | number | null;
  closing_price: string | number | null;
  expiry_minutes: ExpiryMinutes | null;
  calibrated_confidence: number | null;
  grade: SignalGrade;
  status: SignalStatus;
  result: "WON" | "LOST" | "DRAW" | null;
  assets: { symbol: AssetSymbol } | { symbol: AssetSymbol }[] | null;
}

/**
 * Real signal history (spec section 23) -- every real row the signal
 * engine has written that this user is allowed to see (RLS already
 * keeps CANDIDATE/REJECTED admin-only, so this never needs to filter
 * those out itself). A signal whose expiry hasn't passed yet -- or has
 * passed but hasn't been picked up by the resolution job's next cycle
 * -- shows PENDING rather than a blank or a guessed result.
 *
 * Returns an empty array (not null) on any failure so the page can show
 * "0 of 0 records" honestly rather than crash.
 */
export async function getSignalHistory(limit = 500): Promise<HistoryRow[]> {
  try {
    const supabase = await createClient();
    const { data, error } = await supabase
      .from("signals")
      .select(
        "id, direction, generated_at, entry_price, closing_price, expiry_minutes, calibrated_confidence, grade, status, result, assets(symbol)"
      )
      .order("generated_at", { ascending: false })
      .limit(limit);

    if (error || !data) return [];

    return (data as unknown as HistoryRowRaw[]).flatMap((row) => {
      const assetRow = Array.isArray(row.assets) ? row.assets[0] : row.assets;
      if (!assetRow) return [];
      return [{
        id: row.id,
        asset: assetRow.symbol,
        direction: row.direction,
        confidence: row.calibrated_confidence,
        grade: row.grade,
        expiryMinutes: row.expiry_minutes,
        entryPrice: row.entry_price !== null ? Number(row.entry_price) : null,
        closingPrice: row.closing_price !== null ? Number(row.closing_price) : null,
        result: row.result ?? "PENDING",
        status: row.status,
        generatedAt: row.generated_at,
      }];
    });
  } catch {
    return [];
  }
}
