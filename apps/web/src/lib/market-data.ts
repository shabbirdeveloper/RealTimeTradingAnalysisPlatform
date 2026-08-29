import { createClient } from "@/lib/supabase/server";
import type { AssetSymbol, DataStatus } from "@/types";
import { ASSET_LIST } from "@/data/assets";

export interface AssetPriceSnapshot {
  asset: AssetSymbol;
  price: number;
  change24hPct: number;
  dataStatus: DataStatus;
  lastUpdated: string; // ISO
}

const LIVE_MAX_AGE_MS = 10 * 60 * 1000; // 10 minutes
const DELAYED_MAX_AGE_MS = 30 * 60 * 1000; // 30 minutes
const STALE_MAX_AGE_MS = 24 * 60 * 60 * 1000; // 24 hours

function classifyDataStatus(lastCandleTime: Date, now: Date): DataStatus {
  const ageMs = now.getTime() - lastCandleTime.getTime();
  if (ageMs <= LIVE_MAX_AGE_MS) return "LIVE";
  if (ageMs <= DELAYED_MAX_AGE_MS) return "DELAYED";
  if (ageMs <= STALE_MAX_AGE_MS) return "STALE";
  return "OFFLINE";
}

/**
 * Reads real M5 candles from Supabase for each configured asset and
 * derives a price snapshot. An asset with no candles yet (collector
 * hasn't reached it, migrations not run, Supabase not configured) comes
 * back as `null` in the result -- never a fabricated number. Spec
 * section 50: no fake prices, ever, in any state.
 *
 * change24hPct is computed against the OLDEST M5 candle currently
 * stored, not a fixed "24h ago" timestamp -- while the collector is
 * still building up history that may be less than 24 hours' worth. It's
 * still a real, honestly-computed number from real data; it converges to
 * a true 24h figure as history accumulates.
 *
 * Never throws -- any failure (Supabase not configured, network error,
 * RLS denial) results in every asset coming back null, so the caller can
 * render an honest "no data" state instead of the page crashing.
 */
export async function getAssetPriceSnapshots(): Promise<
  Record<AssetSymbol, AssetPriceSnapshot | null>
> {
  const result: Record<AssetSymbol, AssetPriceSnapshot | null> = {
    XAUUSD: null,
    EURUSD: null,
    GBPUSD: null,
  };

  try {
    const supabase = await createClient();
    const now = new Date();

    const { data: assets, error: assetsError } = await supabase
      .from("assets")
      .select("id, symbol")
      .in("symbol", ASSET_LIST);

    if (assetsError || !assets) return result;

    await Promise.all(
      (assets as { id: string; symbol: string }[]).map(async (assetRow) => {
        const symbol = assetRow.symbol as AssetSymbol;
        if (!ASSET_LIST.includes(symbol)) return;

        const [latestResult, oldestResult] = await Promise.all([
          supabase
            .from("candles")
            .select("close, open_time")
            .eq("asset_id", assetRow.id)
            .eq("timeframe", "M5")
            .order("open_time", { ascending: false })
            .limit(1),
          supabase
            .from("candles")
            .select("close, open_time")
            .eq("asset_id", assetRow.id)
            .eq("timeframe", "M5")
            .order("open_time", { ascending: true })
            .limit(1),
        ]);

        const latest = latestResult.data?.[0] as { close: string; open_time: string } | undefined;
        const oldest = oldestResult.data?.[0] as { close: string; open_time: string } | undefined;
        if (!latest) return; // no data for this asset yet -- stays null

        const price = Number(latest.close);
        const baseline = oldest ? Number(oldest.close) : price;
        const change24hPct = baseline !== 0 ? ((price - baseline) / baseline) * 100 : 0;
        const lastCandleTime = new Date(latest.open_time);

        result[symbol] = {
          asset: symbol,
          price,
          change24hPct,
          dataStatus: classifyDataStatus(lastCandleTime, now),
          lastUpdated: lastCandleTime.toISOString(),
        };
      })
    );
  } catch {
    // Leave everything null -- see docstring above.
  }

  return result;
}
