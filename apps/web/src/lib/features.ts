import { createClient } from "@/lib/supabase/server";
import type { AssetSymbol, Timeframe } from "@/types";

export interface RealTechnicalMetrics {
  rsi: number | null;
  rsiSlope: "RISING" | "FALLING" | "FLAT" | null;
  macdHistogram: number | null;
  macdTrend: "EXPANDING" | "CONTRACTING" | null;
  ema20: number | null;
  ema50: number | null;
  ema200: number | null;
  priceVsEma: "ABOVE_ALL" | "BELOW_ALL" | "MIXED" | null;
  atr: number | null;
  atrPercentile: number | null;
  bollingerWidth: number | null;
}

export interface RealStructureReading {
  sequence: "HH_HL" | "LH_LL" | "MIXED" | null;
  bos: boolean;
  choch: boolean;
  support: number | null;
  resistance: number | null;
}

interface FeaturesRow {
  features: {
    trend?: { ema20?: number | null; ema50?: number | null; ema200?: number | null };
    momentum?: {
      rsi14?: number | null;
      rsi_slope?: "RISING" | "FALLING" | "FLAT" | null;
      macd_histogram?: number | null;
      macd_histogram_prev?: number | null;
    };
    volatility?: { atr14?: number | null; atr_percentile?: number | null; bollinger_width_pct?: number | null };
    structure?: {
      sequence?: "HH_HL" | "LH_LL" | "MIXED" | null;
      bos?: boolean;
      choch?: boolean;
      support?: number | null;
      resistance?: number | null;
    };
  };
}

/**
 * Reads the most recently stored real feature snapshot for one
 * asset+timeframe from `market_features` (written by apps/api's feature
 * engine -- see apps/api/app/features/snapshot.py). Returns null when
 * nothing has been computed for this asset/timeframe yet, never a
 * fabricated reading.
 */
export async function getLatestFeatures(
  asset: AssetSymbol,
  timeframe: Timeframe
): Promise<{ technical: RealTechnicalMetrics; structure: RealStructureReading } | null> {
  try {
    const supabase = await createClient();

    const { data: assetRow, error: assetError } = await supabase
      .from("assets")
      .select("id")
      .eq("symbol", asset)
      .maybeSingle();

    if (assetError || !assetRow) return null;

    const { data } = await supabase
      .from("market_features")
      .select("features")
      .eq("asset_id", (assetRow as { id: string }).id)
      .eq("timeframe", timeframe)
      .order("candle_time", { ascending: false })
      .limit(1);

    const row = data?.[0] as FeaturesRow | undefined;
    if (!row) return null;

    const { trend, momentum, volatility, structure } = row.features ?? {};
    const ema20 = trend?.ema20 ?? null;
    const ema50 = trend?.ema50 ?? null;
    const ema200 = trend?.ema200 ?? null;

    const priceVsEma: RealTechnicalMetrics["priceVsEma"] =
      ema20 !== null && ema50 !== null && ema200 !== null
        ? ema20 > ema50 && ema50 > ema200
          ? "ABOVE_ALL"
          : ema20 < ema50 && ema50 < ema200
            ? "BELOW_ALL"
            : "MIXED"
        : null;

    const macdHistogram = momentum?.macd_histogram ?? null;
    const macdHistogramPrev = momentum?.macd_histogram_prev ?? null;
    const macdTrend: RealTechnicalMetrics["macdTrend"] =
      macdHistogram !== null && macdHistogramPrev !== null
        ? Math.abs(macdHistogram) > Math.abs(macdHistogramPrev)
          ? "EXPANDING"
          : "CONTRACTING"
        : null;

    return {
      technical: {
        rsi: momentum?.rsi14 ?? null,
        rsiSlope: momentum?.rsi_slope ?? null,
        macdHistogram,
        macdTrend,
        ema20,
        ema50,
        ema200,
        priceVsEma,
        atr: volatility?.atr14 ?? null,
        atrPercentile: volatility?.atr_percentile ?? null,
        bollingerWidth: volatility?.bollinger_width_pct ?? null,
      },
      structure: {
        sequence: structure?.sequence ?? null,
        bos: structure?.bos ?? false,
        choch: structure?.choch ?? false,
        support: structure?.support ?? null,
        resistance: structure?.resistance ?? null,
      },
    };
  } catch {
    return null;
  }
}
