import type { AssetSymbol, Signal , MarketAssetSymbol } from "@/types";
import { ASSET_LIST } from "./assets";
import { generateSignal } from "./engine";
import { HISTORICAL_SIGNALS } from "./history";

/**
 * Resolves a signal id from either the static demo history, or a live
 * id of the form "ASSET-<5min-bucket>-<expiry|notrade>" by reconstructing
 * the exact timestamp bucket the engine used to generate it deterministically.
 */
export function findSignalById(id: string): Signal | undefined {
  const hist = HISTORICAL_SIGNALS.find((s) => s.id === id);
  if (hist) return hist;

  const match = id.match(/^([A-Z]+)-(\d+)-(.+)$/);
  if (!match) return undefined;
  const asset = match[1] as MarketAssetSymbol;
  const bucket = Number(match[2]);
  if (!ASSET_LIST.includes(asset) || Number.isNaN(bucket)) return undefined;

  const reconstructedNow = new Date(bucket * 5 * 60000 + 60000); // 1 min into the bucket
  return generateSignal(asset, reconstructedNow);
}
