import { ASSET_LIST, ASSET_CONFIGS } from "@/data/assets";
import { AssetSignalCard } from "@/components/dashboard/asset-signal-card";
import { DataStatusPill } from "@/components/shared/badges";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { PERFORMANCE_SUMMARY } from "@/data/history";
import { AnimatedNumber } from "@/components/shared/animated-number";
import { getAssetPriceSnapshots } from "@/lib/market-data";
import { getLatestSignals } from "@/lib/signals";
import { OtcWarning } from "@/components/shared/otc-warning";
import type { AssetSymbol, Signal } from "@/types";
import { Award, TrendingUp, Target, AlertTriangle } from "lucide-react";

export const dynamic = "force-dynamic"; // always read the latest price + signal, never a stale build-time snapshot

/**
 * Real prices AND real signals. apps/api's collector writes real candles;
 * its rule-based signal engine (app/features/signal_engine.py) writes
 * real CALL/PUT/NO_TRADE decisions with a genuine technical score --
 * never a fabricated ML confidence (Phase 6 doesn't exist yet, so
 * `signal.confidence` stays null and grade is capped at B/REJECTED, per
 * spec section 10). The accuracy/streak stat tiles below are still the
 * demo performance engine -- meaningful accuracy stats need real
 * resolved-signal history to accumulate first (spec section 49
 * resolution job isn't built yet), so those stay clearly labeled rather
 * than computed from a handful of untested signals.
 */
export default async function DashboardHomePage() {
  const [snapshots, signals] = await Promise.all([getAssetPriceSnapshots(), getLatestSignals()]);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold tracking-tight text-foreground">Dashboard</h1>
        <p className="text-sm text-muted-foreground">Live analysis across your three configured instruments.</p>
      </div>

      <div className="flex items-start gap-2.5 rounded-lg border border-notrade/20 bg-notrade-muted/40 px-3.5 py-2 text-xs text-notrade-foreground/90">
        <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-notrade" />
        <span>
          <strong className="font-semibold">Prices and signals below are real</strong> — computed from live candles
          by the technical signal engine. There is no calibrated ML confidence yet (Phase 6), so grades are capped at
          B until real models exist. The accuracy/streak figures further down are still{" "}
          <strong className="font-semibold">synthetic placeholders</strong> — real performance tracking needs
          resolved signal history to accumulate first.
        </span>
      </div>

      <OtcWarning />

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <StatTile
          index={0}
          icon={Target}
          label="Overall accuracy"
          value={<AnimatedNumber value={PERFORMANCE_SUMMARY.overallAccuracy} suffix="%" />}
          sub={`${PERFORMANCE_SUMMARY.totalSignals} resolved signals (demo)`}
        />
        <StatTile
          index={1}
          icon={Award}
          label="A++ accuracy"
          value={<AnimatedNumber value={PERFORMANCE_SUMMARY.aPlusPlusAccuracy} suffix="%" />}
          sub={`${PERFORMANCE_SUMMARY.aPlusPlusSignals} A++ signals (demo)`}
          accent
        />
        <StatTile
          index={2}
          icon={TrendingUp}
          label="Current streak"
          value={`${PERFORMANCE_SUMMARY.currentStreak.count} ${PERFORMANCE_SUMMARY.currentStreak.type}`}
          sub={`Max win streak ${PERFORMANCE_SUMMARY.maxWinStreak} (demo)`}
        />
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-5">
        {ASSET_LIST.map((asset, i) => {
          const snapshot = snapshots[asset];
          if (!snapshot) return <NoDataCard key={asset} asset={asset} index={i} />;

          const realSignal = signals[asset];
          const signal: Signal = realSignal ?? {
            id: `${asset}-no-analysis`,
            asset,
            direction: "NO_TRADE",
            confidence: null,
            technicalScore: 0,
            grade: "REJECTED",
            expiryMinutes: null,
            expirySeconds: null,
            marketRegime: "UNSTABLE", // unused -- regimeAvailable={false} below hides it
            generatedAt: snapshot.lastUpdated,
            entryPrice: null,
            validUntil: null,
            reasons: [],
            warnings: [
              "No signal analysis yet for this asset — the engine hasn't completed its first cycle. Price shown is real.",
            ],
            status: "REJECTED",
            modelVersion: null,
            timeframes: [],
            session: "LONDON",
          };

          return (
            <AssetSignalCard
              key={asset}
              signal={signal}
              price={snapshot.price}
              change24hPct={snapshot.change24hPct}
              index={i}
              regimeAvailable={Boolean(realSignal)}
              dataStatus={snapshot.dataStatus}
            />
          );
        })}
      </div>
    </div>
  );
}

function NoDataCard({ asset, index }: { asset: AssetSymbol; index: number }) {
  const cfg = ASSET_CONFIGS[asset];
  return (
    <Card
      className="card-premium-hover h-full animate-in fade-in-0 slide-in-from-bottom-4 duration-500 ease-out"
      style={{ animationDelay: `${index * 90}ms` }}
    >
      <CardHeader className="flex-row items-start justify-between space-y-0 pb-3 pt-4">
        <div>
          <p className="text-sm font-semibold text-foreground">{cfg.displayName}</p>
          <p className="text-xs text-muted-foreground">{cfg.shortName}</p>
        </div>
        <DataStatusPill status="OFFLINE" />
      </CardHeader>
      <CardContent>
        <p className="text-sm text-muted-foreground">
          No live price data yet for this asset. The market-data collector hasn&apos;t reported a candle for it —
          check that it&apos;s running and that the Supabase migrations have been applied.
        </p>
      </CardContent>
    </Card>
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
