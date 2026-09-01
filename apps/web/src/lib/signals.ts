import { createClient } from "@/lib/supabase/server";
import { ASSET_LIST } from "@/data/assets";
import type {
  AssetSymbol, Direction, ExpiryCandidate, ExpiryMinutes, MarketRegime,
  Signal, SignalGrade, SessionName, SignalStatus, TimeframeBias,
} from "@/types";

/**
 * Reads the latest real signal per asset from Supabase's `signals` table
 * (written by apps/api's rule-based signal engine -- see
 * apps/api/app/features/signal_engine.py). Shaped into the same `Signal`
 * type the frontend demo engine already produces, so existing components
 * (AssetSignalCard, LiveSignalCard, MarketPageContent) render it without
 * changes to their own logic.
 *
 * RLS already keeps CANDIDATE/REJECTED rows admin-only (see migration 8),
 * so a plain "latest row for this asset" query naturally returns the
 * latest row this user is allowed to see -- never a row this function
 * has to filter out itself.
 *
 * Never throws -- any failure (no rows yet, Supabase not configured,
 * network error) returns `null` for that asset so callers can fall back
 * to an honest "not analyzed yet" state instead of fake data.
 */
export async function getLatestSignals(): Promise<Record<AssetSymbol, Signal | null>> {
  // Built from ASSET_LIST rather than written out, so adding an asset can
  // never silently leave a key missing here.
  const result = Object.fromEntries(
    ASSET_LIST.map((asset) => [asset, null])
  ) as Record<AssetSymbol, Signal | null>;

  try {
    const supabase = await createClient();

    const { data: assets, error: assetsError } = await supabase
      .from("assets")
      .select("id, symbol")
      .in("symbol", ASSET_LIST);

    if (assetsError || !assets) return result;

    await Promise.all(
      (assets as { id: string; symbol: string }[]).map(async (assetRow) => {
        const symbol = assetRow.symbol as AssetSymbol;
        if (!ASSET_LIST.includes(symbol)) return;

        const { data } = await supabase
          .from("signals")
          .select(
            "id, direction, generated_at, entry_price, expiry_minutes, expiry_seconds, expiry_at, technical_score, calibrated_confidence, grade, market_regime, status, session, reasons, warnings, timeframes_snapshot"
          )
          .eq("asset_id", assetRow.id)
          .order("generated_at", { ascending: false })
          .limit(1);

        const row = data?.[0] as SignalRow | undefined;
        if (!row) return;
        result[symbol] = shapeSignal(symbol, row);
      })
    );
  } catch {
    // Leave everything null -- see docstring above.
  }

  return result;
}

/**
 * Same as getLatestSignals() but for a single asset -- used by the
 * per-market detail page.
 */
export async function getLatestSignal(asset: AssetSymbol): Promise<Signal | null> {
  try {
    const supabase = await createClient();

    const { data: assetRow, error: assetError } = await supabase
      .from("assets")
      .select("id, symbol")
      .eq("symbol", asset)
      .maybeSingle();

    if (assetError || !assetRow) return null;

    const { data } = await supabase
      .from("signals")
      .select(
        "id, direction, generated_at, entry_price, expiry_minutes, expiry_seconds, expiry_at, technical_score, calibrated_confidence, grade, market_regime, status, session, reasons, warnings, timeframes_snapshot"
      )
      .eq("asset_id", (assetRow as { id: string }).id)
      .order("generated_at", { ascending: false })
      .limit(1);

    const row = data?.[0] as SignalRow | undefined;
    if (!row) return null;
    return shapeSignal(asset, row);
  } catch {
    return null;
  }
}

interface SignalRow {
  id: string;
  direction: Direction;
  generated_at: string;
  entry_price: string | number | null;
  expiry_minutes: ExpiryMinutes | null;
  expiry_seconds?: number | null;
  expiry_at: string | null;
  technical_score: number;
  calibrated_confidence: number | null;
  grade: SignalGrade;
  market_regime: MarketRegime;
  status: SignalStatus;
  session: SessionName;
  reasons: string[] | null;
  warnings: string[] | null;
  timeframes_snapshot: {
    timeframes?: TimeframeBias[];
    candidates?: {
      expiry_minutes?: ExpiryMinutes | null;
      expiry_seconds?: number | null;
      direction: Direction;
      technical_score: number;
      grade: SignalGrade;
      rejection_reason?: string | null;
    }[];
    regime_reason?: string;
  } | null;
}

function shapeSignal(asset: AssetSymbol, row: SignalRow): Signal {
  const timeframes = row.timeframes_snapshot?.timeframes ?? [];
  const rawCandidates = row.timeframes_snapshot?.candidates ?? [];

  const candidates: ExpiryCandidate[] | undefined = rawCandidates.length
    ? rawCandidates.map((c) => ({
        expiryMinutes: (c.expiry_minutes ?? null) as ExpiryMinutes,
        // The engine writes seconds; older snapshots carry minutes only.
        expirySeconds: c.expiry_seconds ?? (c.expiry_minutes != null ? c.expiry_minutes * 60 : null),
        direction: c.direction,
        technicalScore: c.technical_score,
        modelConfidence: null,
        modelStatus: "MODEL_NOT_READY",
        metaDecision: null,
        grade: c.grade,
      }))
    : undefined;

  return {
    id: row.id,
    asset,
    direction: row.direction,
    confidence: row.calibrated_confidence,
    technicalScore: row.technical_score,
    grade: row.grade,
    expiryMinutes: row.expiry_minutes,
    expirySeconds: row.expiry_seconds ?? (row.expiry_minutes != null ? row.expiry_minutes * 60 : null),
    marketRegime: row.market_regime,
    generatedAt: row.generated_at,
    entryPrice: row.entry_price !== null ? Number(row.entry_price) : null,
    validUntil: row.expiry_at,
    reasons: row.reasons ?? [],
    warnings: row.warnings ?? [],
    status: row.status,
    modelVersion: null, // Phase 6 (ML) not built -- never fabricated
    timeframes,
    session: row.session,
    candidates,
  };
}
