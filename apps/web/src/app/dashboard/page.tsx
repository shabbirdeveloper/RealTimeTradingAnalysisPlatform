import { ASSET_LIST, ASSET_CONFIGS } from "@/data/assets";
import { AssetSignalCard } from "@/components/dashboard/asset-signal-card";
import { DataStatusPill } from "@/components/shared/badges";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { getRealPerformanceSummary } from "@/lib/performance";
import { breakEvenWinRate, wilsonInterval } from "@/lib/statistics";
import { AnimatedNumber } from "@/components/shared/animated-number";
import { getAssetPriceSnapshotsWithReason } from "@/lib/market-data";
import { getLatestSignals, getLastEvaluationTimes } from "@/lib/signals";
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
 * spec section 10).
 *
 * The stat tiles are computed from REAL resolved signals only. They used
 * to render the demo performance engine's numbers with "(demo)" appended,
 * which was honest but useless: a fabricated 71% is not a smaller version
 * of a real one, and a headline figure invites being read as real however
 * it is labelled. Now the resolution job exists, so the tiles show what
 * has actually resolved -- including "nothing yet", which is a true
 * answer and the correct one on day one.
 */
export default async function DashboardHomePage() {
  const summary = await getRealPerformanceSummary();
  const wins = summary?.wins ?? 0;
  const losses = summary?.losses ?? 0;
  const decided = wins + losses;
  const accuracy = decided > 0 ? Math.round((wins / decided) * 1000) / 10 : 0;
  const ci = decided > 0 ? wilsonInterval(wins, decided) : null;
  const breakEven = Math.round(breakEvenWinRate(80) * 10) / 10;

  // The verdict reads the LOWER interval bound against break-even, never the
  // point estimate. A 62% win rate on 20 trades spans roughly 41-79%, which
  // is not evidence of an edge -- and a dashboard that calls that "profitable"
  // is the exact failure this project set out not to have.
  const verdict =
    decided < 30 ? "Too early"
    : ci!.low > breakEven ? "Profitable"
    : ci!.high < breakEven ? "Losing"
    : "Unproven";
  const verdictClass =
    verdict === "Profitable" ? "text-call"
    : verdict === "Losing" ? "text-put"
    : "text-muted-foreground";

  const [priceData, signals, evaluatedAt] = await Promise.all([
    getAssetPriceSnapshotsWithReason(),
    getLatestSignals(),
    getLastEvaluationTimes(),
  ]);
  const { snapshots, failure: dataFailure } = priceData;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold tracking-tight text-foreground">Dashboard</h1>
        <p className="text-sm text-muted-foreground">Live analysis across your {ASSET_LIST.length} configured instruments.</p>
      </div>

      <div className="flex items-start gap-2.5 rounded-lg border border-notrade/20 bg-notrade-muted/40 px-3.5 py-2 text-xs text-notrade-foreground/90">
        <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-notrade" />
        <span>
          <strong className="font-semibold">Everything below is real</strong> — prices, signals and accuracy are
          computed from live candles and resolved outcomes. There is no calibrated ML confidence yet (Phase 6), so
          grades are capped at B until trained models exist. Accuracy is measured on a small number of resolved
          signals so far; read the interval, not the headline figure.
        </span>
      </div>

      <OtcWarning />

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <StatTile
          index={0}
          icon={Target}
          label="Overall accuracy"
          value={
            decided > 0
              ? <AnimatedNumber value={accuracy} suffix="%" />
              : <span className="text-muted-foreground">—</span>
          }
          sub={
            decided > 0
              ? `${decided} resolved · 95% CI ${ci!.low.toFixed(0)}\u2013${ci!.high.toFixed(0)}%`
              : "No signals resolved yet"
          }
        />
        <StatTile
          index={1}
          icon={Award}
          label="Break-even"
          value={<AnimatedNumber value={breakEven} suffix="%" />}
          sub="Needed at an 80% payout"
          accent
        />
        <StatTile
          index={2}
          icon={TrendingUp}
          label="Verdict"
          value={
            <span className={verdictClass}>{verdict}</span>
          }
          sub={
            decided > 0
              ? `${summary?.wins ?? 0}W / ${summary?.losses ?? 0}L`
              : "Needs ~30 resolved to say anything"
          }
        />
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-5">
        {ASSET_LIST.map((asset, i) => {
          const snapshot = snapshots[asset];
          if (!snapshot) return <NoDataCard key={asset} asset={asset} index={i} failure={dataFailure} />;

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
              lastEvaluatedAt={evaluatedAt[asset] ?? null}
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

function NoDataCard({ asset, index, failure }: { asset: AssetSymbol; index: number; failure?: { reason: string } | null }) {
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
        {failure ? (
          <>
            <p className="text-sm text-destructive">
              Price data could not be read. This is an access or setup problem, not an empty
              database — the candles may well be there.
            </p>
            <p className="mt-2 break-words font-mono-tabular text-[11px] text-muted-foreground">
              {failure.reason}
            </p>
          </>
        ) : (
          <p className="text-sm text-muted-foreground">
            No candle has ever been stored for this asset. Start the market-data collector, and
            check that the Supabase migrations have been applied.
          </p>
        )}
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
