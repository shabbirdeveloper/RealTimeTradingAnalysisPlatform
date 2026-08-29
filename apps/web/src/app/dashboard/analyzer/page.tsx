import { getLatestSignals } from "@/lib/signals";
import { AnalyzerView } from "@/components/dashboard/analyzer-view";

export const dynamic = "force-dynamic";

export default async function AnalyzerPage() {
  const signals = await getLatestSignals();

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div>
        <h1 className="text-xl font-semibold tracking-tight text-foreground">Analyzer</h1>
        <p className="text-sm text-muted-foreground">Real analysis for any asset / expiry combination, from the latest signal-engine cycle.</p>
      </div>

      <AnalyzerView signals={signals} />
    </div>
  );
}
