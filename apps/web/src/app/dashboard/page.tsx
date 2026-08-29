"use client";
import { useNow } from "@/lib/use-now";
import { ASSET_LIST } from "@/data/assets";
import { generateSignal, generateMarketSnapshot } from "@/data/engine";
import { AssetSignalCard } from "@/components/dashboard/asset-signal-card";
import { DemoDataBanner } from "@/components/shared/badges";
import { Skeleton } from "@/components/ui/skeleton";
import { Card, CardContent } from "@/components/ui/card";
import { PERFORMANCE_SUMMARY } from "@/data/history";
import { AnimatedNumber } from "@/components/shared/animated-number";
import { Award, TrendingUp, Target } from "lucide-react";

export default function DashboardHomePage() {
  const now = useNow(1000);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold tracking-tight text-foreground">Dashboard</h1>
        <p className="text-sm text-muted-foreground">Live analysis across your three configured instruments.</p>
      </div>

      <DemoDataBanner />

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <StatTile
          index={0}
          icon={Target}
          label="Overall accuracy"
          value={<AnimatedNumber value={PERFORMANCE_SUMMARY.overallAccuracy} suffix="%" />}
          sub={`${PERFORMANCE_SUMMARY.totalSignals} resolved signals`}
        />
        <StatTile
          index={1}
          icon={Award}
          label="A++ accuracy"
          value={<AnimatedNumber value={PERFORMANCE_SUMMARY.aPlusPlusAccuracy} suffix="%" />}
          sub={`${PERFORMANCE_SUMMARY.aPlusPlusSignals} A++ signals`}
          accent
        />
        <StatTile
          index={2}
          icon={TrendingUp}
          label="Current streak"
          value={`${PERFORMANCE_SUMMARY.currentStreak.count} ${PERFORMANCE_SUMMARY.currentStreak.type}`}
          sub={`Max win streak ${PERFORMANCE_SUMMARY.maxWinStreak}`}
        />
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
        {now
          ? ASSET_LIST.map((asset, i) => {
              const signal = generateSignal(asset, now);
              const snapshot = generateMarketSnapshot(asset, now);
              return (
                <AssetSignalCard
                  key={asset}
                  signal={signal}
                  price={snapshot.price}
                  change24hPct={snapshot.change24hPct}
                  index={i}
                />
              );
            })
          : ASSET_LIST.map((asset) => <Skeleton key={asset} className="h-52" />)}
      </div>
    </div>
  );
}

function StatTile({
  icon: Icon,
  label,
  value,
  sub,
  accent,
  index = 0,
}: {
  icon: typeof Target;
  label: string;
  value: React.ReactNode;
  sub: string;
  accent?: boolean;
  index?: number;
}) {
  return (
    <Card
      className="card-premium-hover animate-in fade-in-0 slide-in-from-bottom-3 duration-500 ease-out"
      style={{ animationDelay: `${index * 90}ms` }}
    >
      <CardContent className="flex items-center gap-3.5 p-4">
        <span
          className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-lg ring-1 ring-inset ${
            accent ? "bg-gradient-to-br from-aplusplus/25 to-aplusplus/5 text-aplusplus ring-aplusplus/25" : "bg-gradient-to-br from-primary/20 to-primary/5 text-primary ring-primary/20"
          }`}
        >
          <Icon className="h-4.5 w-4.5" />
        </span>
        <div>
          <p className="text-[10.5px] font-medium uppercase tracking-wider text-muted-foreground">{label}</p>
          <p className="font-mono-tabular text-lg font-semibold text-foreground">{value}</p>
          <p className="text-[11px] text-muted-foreground">{sub}</p>
        </div>
      </CardContent>
    </Card>
  );
}
