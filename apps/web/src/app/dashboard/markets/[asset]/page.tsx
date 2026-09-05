import { notFound } from "next/navigation";
import { MarketPageContent } from "@/components/dashboard/market-page-content";
import { getAssetPriceSnapshot } from "@/lib/market-data";
import { getLatestSignal } from "@/lib/signals";
import { getLatestFeatures } from "@/lib/features";
import type { MarketAssetSymbol } from "@/types";

// Real-market routes only. Broker-generated instruments are rendered on
// the dashboard's own OTC section, not here: this page's fallbacks are
// seeded from real-market demo data that has no synthetic equivalent.
const SLUG_MAP: Record<string, MarketAssetSymbol> = {
  xauusd: "XAUUSD",
  eurusd: "EURUSD",
  gbpusd: "GBPUSD",
  btcusd: "BTCUSD",
  ethusd: "ETHUSD",
};

export function generateStaticParams() {
  return Object.keys(SLUG_MAP).map((asset) => ({ asset }));
}

export const dynamic = "force-dynamic"; // always read the latest price/signal/features, never a stale build-time snapshot

export default async function MarketPage({ params }: { params: Promise<{ asset: string }> }) {
  const { asset: assetParam } = await params;
  const asset: MarketAssetSymbol = SLUG_MAP[assetParam.toLowerCase()];
  if (!asset) notFound();

  const [priceSnapshot, signal, features] = await Promise.all([
    getAssetPriceSnapshot(asset),
    getLatestSignal(asset),
    getLatestFeatures(asset, "H1"),
  ]);

  return <MarketPageContent asset={asset} priceSnapshot={priceSnapshot} signal={signal} features={features} />;
}
