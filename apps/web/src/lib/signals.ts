import { createClient } from "@/lib/supabase/server";
import { ASSET_LIST, OTC_ASSET_LIST } from "@/data/assets";
import type {
  AssetSymbol, Direction, ExpiryCandidate, ExpiryMinutes, MarketAssetSymbol,
  MarketRegime, Signal, SignalGrade, SessionName, SignalStatus, TimeframeBias,
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

    // One query, not one per asset plus a lookup. This was six round trips
    // from Vercel to Supabase for five rows; the join comes back with the
    // symbol so the asset table is not fetched separately, and the first
    // row seen per symbol is the newest because of the ORDER BY.
    //
    // A modest limit is enough: even at five assets it only has to reach
    // back far enough to see each symbol once, and the
    // (asset_id, last_evaluated_at desc) index added in migration 23 makes
    // that ordering cheap.
    const { data, error } = await supabase
      .from("signals")
      .select(
        "id, direction, generated_at, last_evaluated_at, entry_price, expiry_minutes, expiry_seconds, expiry_at, technical_score, call_score, put_score, calibrated_confidence, grade, market_regime, status, session, reasons, warnings, timeframes_snapshot, assets!inner(symbol)"
      )
      .order("last_evaluated_at", { ascending: false, nullsFirst: false })
      .limit(200);

    if (error || !data) return result;

    for (const raw of data as Array<SignalRow & { assets: { symbol: string } | { symbol: string }[] }>) {
      const assetRow = Array.isArray(raw.assets) ? raw.assets[0] : raw.assets;
      const symbol = assetRow?.symbol as MarketAssetSymbol | undefined;
      if (!symbol || !ASSET_LIST.includes(symbol)) continue;
      if (result[symbol]) continue; // already have this asset's newest
      result[symbol] = shapeSignal(symbol, raw);
    }
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
        "id, direction, generated_at, last_evaluated_at, entry_price, expiry_minutes, expiry_seconds, expiry_at, technical_score, call_score, put_score, calibrated_confidence, grade, market_regime, status, session, reasons, warnings, timeframes_snapshot"
      )
      .eq("asset_id", (assetRow as { id: string }).id)
      .order("last_evaluated_at", { ascending: false, nullsFirst: false })
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
  last_evaluated_at?: string | null;
  entry_price: string | number | null;
  expiry_minutes: ExpiryMinutes | null;
  expiry_seconds?: number | null;
  expiry_at: string | null;
  technical_score: number;
  call_score?: number | null;
  put_score?: number | null;
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
    checks?: {
      name: string; passed: boolean; detail: string;
      value?: string | null; required?: string | null;
    }[];
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
    callScore: row.call_score ?? null,
    putScore: row.put_score ?? null,
    grade: row.grade,
    checks: (row.timeframes_snapshot?.checks ?? []).map((c) => ({
      name: c.name,
      passed: c.passed,
      detail: c.detail,
      value: c.value ?? null,
      required: c.required ?? null,
    })),
    expiryMinutes: row.expiry_minutes,
    expirySeconds: row.expiry_seconds ?? (row.expiry_minutes != null ? row.expiry_minutes * 60 : null),
    marketRegime: row.market_regime,
    generatedAt: row.generated_at,
    lastEvaluatedAt: row.last_evaluated_at ?? null,
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

/**
 * When each asset was last evaluated, whatever the outcome.
 *
 * Needed because REJECTED decisions are hidden from non-admins, so the
 * newest row a user can SEE may be much older than the newest row that
 * exists. Without this the dashboard reports a working engine as a
 * stopped one — see migration 22.
 */
export async function getLastEvaluationTimes(): Promise<Record<string, string>> {
  try {
    const supabase = await createClient();
    const { data, error } = await supabase.rpc("latest_evaluation_times");
    if (error || !data) return {};
    return Object.fromEntries(
      (data as Array<{ symbol: string; last_evaluated_at: string }>).map((r) => [
        r.symbol,
        r.last_evaluated_at,
      ])
    );
  } catch {
    return {};
  }
}

/**
 * Latest decision per broker-OTC instrument.
 *
 * A separate query from getLatestSignals() rather than a widened one, for
 * the reason spec section 72 gives: these must never be pooled with
 * real-market results. Two functions make mixing them a deliberate act; one
 * function with a list parameter makes it a typo.
 */
export async function getLatestOtcSignals(): Promise<Record<string, Signal | null>> {
  const result: Record<string, Signal | null> = Object.fromEntries(
    OTC_ASSET_LIST.map((a) => [a, null])
  );

  try {
    const supabase = await createClient();
    const { data, error } = await supabase
      .from("signals")
      .select(
        "id, direction, generated_at, last_evaluated_at, entry_price, expiry_minutes, expiry_seconds, expiry_at, technical_score, call_score, put_score, calibrated_confidence, grade, market_regime, status, session, reasons, warnings, timeframes_snapshot, assets!inner(symbol, market_type)"
      )
      .order("last_evaluated_at", { ascending: false, nullsFirst: false })
      .limit(200);

    if (error || !data) return result;

    for (const raw of data as Array<
      SignalRow & { assets: { symbol: string } | { symbol: string }[] }
    >) {
      const assetRow = Array.isArray(raw.assets) ? raw.assets[0] : raw.assets;
      const symbol = assetRow?.symbol;
      if (!symbol || !(symbol in result)) continue;
      if (result[symbol]) continue; // already have this instrument's newest
      result[symbol] = shapeSignal(symbol as AssetSymbol, raw);
    }
  } catch {
    // Leave everything null -- an honest empty state, never a fabricated one.
  }

  return result;
}
