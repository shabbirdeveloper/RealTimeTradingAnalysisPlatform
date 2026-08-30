"use client";
import { useNow } from "@/lib/use-now";
import { ASSET_LIST, ASSET_CONFIGS } from "@/data/assets";
import { LiveSignalCard } from "@/components/dashboard/live-signal-card";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import type { AssetSymbol, Signal } from "@/types";
import { SignalAlerts } from "@/components/dashboard/signal-alerts";

/**
 * Client wrapper around the real signals fetched server-side (see
 * app/dashboard/signals/page.tsx) -- exists only so LiveSignalCard's
 * "Valid for 00:35" countdown can keep ticking without needing an API
 * round-trip. The signals themselves are real; only the current-time
 * clock used to render the countdown is client-side.
 */
export function LiveSignalsGrid({ signals }: { signals: Record<AssetSymbol, Signal | null> }) {
  const now = useNow(1000);

  if (!now) {
    return (
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2 xl:grid-cols-3">
        {ASSET_LIST.map((asset) => (
          <Skeleton key={asset} className="h-72" />
        ))}
      </div>
    );
  }

  return (
    <>
      <SignalAlerts signals={signals} />
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2 xl:grid-cols-3">
        {ASSET_LIST.map((asset, i) => {
          const signal = signals[asset];
          if (!signal) return <NoSignalCard key={asset} asset={asset} index={i} />;
          return <LiveSignalCard key={asset} signal={signal} now={now} index={i} />;
        })}
      </div>
    </>
  );
}

function NoSignalCard({ asset, index }: { asset: AssetSymbol; index: number }) {
  const cfg = ASSET_CONFIGS[asset];
  return (
    <Card
      className="card-premium-hover h-full animate-in fade-in-0 slide-in-from-bottom-4 duration-500 ease-out"
      style={{ animationDelay: `${index * 90}ms` }}
    >
      <CardContent className="space-y-2 p-5">
        <p className="text-base font-semibold text-foreground">{cfg.displayName}</p>
        <p className="text-sm text-muted-foreground">
          No signal analysis yet for this asset — the signal engine hasn&apos;t completed its first cycle, or there
          isn&apos;t enough real candle history yet. Check back after the next 5-minute analysis cycle.
        </p>
      </CardContent>
    </Card>
  );
}
