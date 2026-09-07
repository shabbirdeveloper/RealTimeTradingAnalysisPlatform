import { getLastEvaluationTimes, getLatestSignals } from "@/lib/signals";
import { LiveSignalsGrid } from "@/components/dashboard/live-signals-grid";
import { staleNoteForRealMarket } from "@/lib/engine-status";
import { OtcWarning } from "@/components/shared/otc-warning";

export const dynamic = "force-dynamic"; // always read the latest signal, never a stale build-time snapshot

export default async function LiveSignalsPage() {
  // Both, in parallel. The second is not optional: REJECTED decisions are
  // hidden from non-admins, so the newest row a reader can SEE may be days
  // older than the newest row that EXISTS -- and the card would then
  // announce that a perfectly healthy engine had stopped.
  const [signals, lastEvaluated] = await Promise.all([
    getLatestSignals(),
    getLastEvaluationTimes(),
  ]);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold tracking-tight text-foreground">Live Signals</h1>
        <p className="text-sm text-muted-foreground">Refreshes on a 5-minute analysis cycle. Quality over quantity — most cycles produce NO TRADE.</p>
      </div>

      <OtcWarning />

      <LiveSignalsGrid
        signals={signals}
        lastEvaluated={lastEvaluated}
        staleNote={staleNoteForRealMarket()}
      />
    </div>
  );
}
