import { getRealPerformanceSummary } from "@/lib/performance";
import { PerformanceCharts } from "@/components/dashboard/performance-charts";
import { DemoDataBanner } from "@/components/shared/badges";

export const dynamic = "force-dynamic";

export default async function PerformancePage() {
  const summary = await getRealPerformanceSummary();

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold tracking-tight text-foreground">Performance</h1>
        <p className="text-sm text-muted-foreground">
          {summary
            ? "Calculated from real resolved signals only — never a claimed number that outruns actual results."
            : "Calculated from recorded demo results only — never a claimed live win rate."}
        </p>
      </div>

      {summary ? <PerformanceCharts summary={summary} /> : <DemoDataBanner />}
    </div>
  );
}
