import { notFound } from "next/navigation";
import { MarketPageContent } from "@/components/dashboard/market-page-content";
import type { AssetSymbol } from "@/types";

const SLUG_MAP: Record<string, AssetSymbol> = {
  xauusd: "XAUUSD",
  eurusd: "EURUSD",
  gbpusd: "GBPUSD",
};

export function generateStaticParams() {
  return Object.keys(SLUG_MAP).map((asset) => ({ asset }));
}

export default async function MarketPage({ params }: { params: Promise<{ asset: string }> }) {
  const { asset: assetParam } = await params;
  const asset = SLUG_MAP[assetParam.toLowerCase()];
  if (!asset) notFound();
  return <MarketPageContent asset={asset} />;
}
