"use client";
import { useNow } from "@/lib/use-now";
import { ASSET_LIST } from "@/data/assets";
import { generateSignal } from "@/data/engine";
import { LiveSignalCard } from "@/components/dashboard/live-signal-card";
import { DemoDataBanner } from "@/components/shared/badges";
import { Skeleton } from "@/components/ui/skeleton";

export default function LiveSignalsPage() {
  const now = useNow(1000);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold tracking-tight text-foreground">Live Signals</h1>
        <p className="text-sm text-muted-foreground">Refreshes on a 5-minute analysis cycle. Quality over quantity — most cycles produce NO TRADE.</p>
      </div>

      <DemoDataBanner />

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2 xl:grid-cols-3">
        {now
          ? ASSET_LIST.map((asset, i) => (
              <LiveSignalCard key={asset} signal={generateSignal(asset, now)} now={now} index={i} />
            ))
          : ASSET_LIST.map((asset) => <Skeleton key={asset} className="h-72" />)}
      </div>
    </div>
  );
}
