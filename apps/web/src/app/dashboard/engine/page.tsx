import { EngineMonitor } from "@/components/dashboard/engine-monitor";
import { EvaluateButton } from "@/components/dashboard/evaluate-button";
import { ASSET_CONFIGS, ASSET_LIST, OTC_ASSET_LIST } from "@/data/assets";
import { getEngineSnapshot } from "@/lib/engine-monitor";

export const dynamic = "force-dynamic";

/**
 * The engine's own view of itself.
 *
 * Every other page shows what the engine DECIDED. This one shows what it
 * SAW and why it declined, which on a selective engine is almost all of
 * the output — most cycles end in no trade, and that is the platform's
 * thesis rather than a fault.
 *
 * It exists because a page that only shows accepted signals shows almost
 * nothing, and "my dashboard never changes" leads to exactly two
 * responses: distrust the system, or lower the quality bar until it
 * speaks. The second is how a signal platform starts losing money
 * confidently, and it is the failure this page is meant to prevent.
 */
export default async function EnginePage() {
  const snapshot = await getEngineSnapshot();

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-semibold tracking-tight text-foreground">Engine</h1>
        <p className="text-sm text-muted-foreground">
          The 5-minute OTC engine, cycle by cycle — including every setup it declined.
        </p>
      </div>

      <div className="rounded-lg border border-border bg-card/40 px-3.5 py-2.5 text-xs leading-relaxed text-muted-foreground">
        A high decline count is the engine working, not failing. It evaluates
        every 30 seconds and publishes only when the evidence clears both the
        score floor and the separation floor, so most cycles end in no trade.
        The figures here are counted from stored decisions — nothing is estimated.
      </div>

      <section className="space-y-3">
        <div>
          <h2 className="text-sm font-semibold text-foreground">Analyse now</h2>
          <p className="text-xs text-muted-foreground">
            Runs the same evaluation the scheduler runs, on the same closed bars.
            Most of the time the answer is NO TRADE — that is the engine working.
            If the entry bar has not closed since the last run, the answer cannot
            change and it will say so.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {[...ASSET_LIST, ...OTC_ASSET_LIST].map((symbol) => (
            <EvaluateButton
              key={symbol}
              symbol={symbol}
              label={ASSET_CONFIGS[symbol].displayName}
            />
          ))}
        </div>
      </section>

      <EngineMonitor snapshot={snapshot} />
    </div>
  );
}
