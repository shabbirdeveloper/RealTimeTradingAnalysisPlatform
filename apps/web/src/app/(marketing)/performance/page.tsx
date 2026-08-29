import { PERFORMANCE_SUMMARY } from "@/data/history";
import { Card, CardContent } from "@/components/ui/card";
import { DemoDataBanner } from "@/components/shared/badges";
import { formatPercent } from "@/lib/utils";

const p = PERFORMANCE_SUMMARY;

export default function PublicPerformancePage() {
  return (
    <div className="container max-w-3xl py-16">
      <h1 className="text-3xl font-semibold text-foreground">Performance is measured, not marketed</h1>
      <p className="mt-3 text-muted-foreground">
        We distinguish overall accuracy from A++ accuracy, and only display numbers calculated from actual recorded
        results. No hard-coded 90% claims.
      </p>

      <div className="mt-6"><DemoDataBanner /></div>

      <div className="mt-8 grid grid-cols-1 gap-4 sm:grid-cols-2">
        <Card>
          <CardContent className="p-6">
            <p className="text-xs uppercase tracking-wide text-muted-foreground">All signals</p>
            <p className="mt-1 font-mono-tabular text-3xl font-semibold text-foreground">{formatPercent(p.overallAccuracy)}</p>
            <p className="mt-1 text-sm text-muted-foreground">{p.totalSignals} resolved signals</p>
          </CardContent>
        </Card>
        <Card className="border-aplusplus/40">
          <CardContent className="p-6">
            <p className="text-xs uppercase tracking-wide text-muted-foreground">A++ signals</p>
            <p className="mt-1 font-mono-tabular text-3xl font-semibold text-aplusplus">{formatPercent(p.aPlusPlusAccuracy)}</p>
            <p className="mt-1 text-sm text-muted-foreground">{p.aPlusPlusSignals} A++ signals</p>
          </CardContent>
        </Card>
      </div>

      <p className="mt-8 text-sm text-muted-foreground">
        Full breakdowns by asset, expiry, session, market regime and confidence bucket are available inside the{" "}
        <a href="/dashboard/performance" className="text-primary underline">dashboard</a> after you sign in.
      </p>
    </div>
  );
}
