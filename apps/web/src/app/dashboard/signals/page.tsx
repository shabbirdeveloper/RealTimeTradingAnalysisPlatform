import { getLatestSignals } from "@/lib/signals";
import { LiveSignalsGrid } from "@/components/dashboard/live-signals-grid";

export const dynamic = "force-dynamic"; // always read the latest signal, never a stale build-time snapshot

export default async function LiveSignalsPage() {
  const signals = await getLatestSignals();

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold tracking-tight text-foreground">Live Signals</h1>
        <p className="text-sm text-muted-foreground">Refreshes on a 5-minute analysis cycle. Quality over quantity — most cycles produce NO TRADE.</p>
      </div>

      <LiveSignalsGrid signals={signals} />
    </div>
  );
}
