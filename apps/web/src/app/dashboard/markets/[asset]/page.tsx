import { notFound } from "next/navigation";
import { MarketPageContent } from "@/components/dashboard/market-page-content";
import { getAssetPriceSnapshot } from "@/lib/market-data";
import { getLatestSignal } from "@/lib/signals";
import { getLatestFeatures } from "@/lib/features";
import type { AssetSymbol } from "@/types";

const SLUG_MAP: Record<string, AssetSymbol> = {
  xauusd: "XAUUSD",
  eurusd: "EURUSD",
  gbpusd: "GBPUSD",
};

export function generateStaticParams() {
  return Object.keys(SLUG_MAP).map((asset) => ({ asset }));
}

export const dynamic = "force-dynamic"; // always read the latest price/signal/features, never a stale build-time snapshot

export default async function MarketPage({ params }: { params: Promise<{ asset: string }> }) {
  const { asset: assetParam } = await params;
  const asset = SLUG_MAP[assetParam.toLowerCase()];
  if (!asset) notFound();

  const [priceSnapshot, signal, features] = await Promise.all([
    getAssetPriceSnapshot(asset),
    getLatestSignal(asset),
    getLatestFeatures(asset, "H1"),
  ]);

  return <MarketPageContent asset={asset} priceSnapshot={priceSnapshot} signal={signal} features={features} />;
}
