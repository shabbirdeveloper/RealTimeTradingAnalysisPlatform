import { wilsonInterval } from "@/lib/statistics";
import type { ThresholdBucket } from "@/lib/admin";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

/**
 * Win rate by technical score, accepted signals against the counterfactual
 * outcomes of setups the engine rejected.
 *
 * This is the readout that makes the quality threshold falsifiable. Until
 * shadow resolution existed, only the left column was measurable — so there
 * was no way to tell whether the cutoff was selecting good setups or simply
 * discarding a random half of them.
 */
export function ThresholdCurve({ buckets }: { buckets: ThresholdBucket[] }) {
  const total = buckets.reduce(
    (n, b) => n + b.accepted.wins + b.accepted.losses + b.rejected.wins + b.rejected.losses, 0
  );

  return (
    <Card>
      <CardHeader>
        <CardTitle>Threshold curve</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <p className="text-xs text-muted-foreground">
          Rejected outcomes are counterfactual — what would have happened had the setup been taken. They never count
          toward reported accuracy. If both columns read the same, the threshold isn&apos;t selecting anything.
        </p>

        {total === 0 ? (
          <p className="rounded-md border border-dashed border-border bg-secondary/20 p-3 text-sm text-muted-foreground">
            No resolved outcomes yet. This fills in as signals reach expiry — roughly a day for the first rows,
            a few weeks before the buckets carry enough weight to act on.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[520px] text-sm">
              <thead>
                <tr className="border-b border-border text-[11px] uppercase tracking-wide text-muted-foreground">
                  <th className="py-2 text-left font-medium">Score</th>
                  <th className="py-2 text-right font-medium">Taken</th>
                  <th className="py-2 text-right font-medium">Win rate</th>
                  <th className="py-2 text-right font-medium">Declined</th>
                  <th className="py-2 text-right font-medium">Would have won</th>
                </tr>
              </thead>
              <tbody>
                {buckets.map((b) => (
                  <Row key={b.label} bucket={b} />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function Row({ bucket }: { bucket: ThresholdBucket }) {
  const a = bucket.accepted.wins + bucket.accepted.losses;
  const r = bucket.rejected.wins + bucket.rejected.losses;
  const aRate = a > 0 ? (bucket.accepted.wins / a) * 100 : null;
  const rRate = r > 0 ? (bucket.rejected.wins / r) * 100 : null;
  const aCi = a > 0 ? wilsonInterval(bucket.accepted.wins, a) : null;
  const rCi = r > 0 ? wilsonInterval(bucket.rejected.wins, r) : null;

  return (
    <tr className="border-b border-border/60">
      <td className="py-2 font-medium text-foreground">{bucket.label}</td>
      <td className="py-2 text-right font-mono-tabular text-muted-foreground">{a || "—"}</td>
      <td className="py-2 text-right font-mono-tabular">
        {aRate === null ? <span className="text-muted-foreground">—</span> : (
          <>
            {aRate.toFixed(0)}%
            <span className="ml-1.5 text-[11px] text-muted-foreground">
              {aCi!.low.toFixed(0)}–{aCi!.high.toFixed(0)}
            </span>
          </>
        )}
      </td>
      <td className="py-2 text-right font-mono-tabular text-muted-foreground">{r || "—"}</td>
      <td className="py-2 text-right font-mono-tabular">
        {rRate === null ? <span className="text-muted-foreground">—</span> : (
          <>
            {rRate.toFixed(0)}%
            <span className="ml-1.5 text-[11px] text-muted-foreground">
              {rCi!.low.toFixed(0)}–{rCi!.high.toFixed(0)}
            </span>
          </>
        )}
      </td>
    </tr>
  );
}
