"use client";

import { useState } from "react";
import { wilsonInterval } from "@/lib/statistics";
import type { ThresholdBucket, ThresholdCurveReport, ThresholdCurveSlice } from "@/lib/admin";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";

/**
 * Win rate by technical score, accepted signals against the counterfactual
 * outcomes of setups the engine rejected.
 *
 * This is the readout that makes the quality threshold falsifiable. Until
 * shadow resolution existed, only the left column was measurable — so there
 * was no way to tell whether the cutoff was selecting good setups or simply
 * discarding a random half of them.
 *
 * It is split by asset and by expiry because a single pooled curve answers
 * the wrong question. Spec section 4: the same parameters should not be
 * assumed to work across assets. Pooled, a well-behaved gold curve and a
 * badly-behaved cable curve average into a mediocre middle, and the single
 * threshold you set from it is wrong for both.
 */
export function ThresholdCurve({ report }: { report: ThresholdCurveReport }) {
  const views: { id: string; label: string; slices: ThresholdCurveSlice[] }[] = [
    { id: "all", label: "All", slices: [report.overall] },
    ...(report.byAsset.length > 0
      ? [{ id: "asset", label: "By asset", slices: report.byAsset }]
      : []),
    ...(report.byExpiry.length > 0
      ? [{ id: "expiry", label: "By expiry", slices: report.byExpiry }]
      : []),
  ];

  const [viewId, setViewId] = useState("all");
  const view = views.find((v) => v.id === viewId) ?? views[0];
  const mixedRuleSets = report.strategyVersions.length > 1;

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between gap-4 space-y-0">
        <CardTitle>Threshold curve</CardTitle>
        {views.length > 1 && (
          <div className="flex gap-1 rounded-md border border-border p-0.5">
            {views.map((v) => (
              <button
                key={v.id}
                type="button"
                onClick={() => setViewId(v.id)}
                className={cn(
                  "rounded px-2.5 py-1 text-xs transition-colors",
                  v.id === view.id
                    ? "bg-secondary text-foreground"
                    : "text-muted-foreground hover:text-foreground"
                )}
              >
                {v.label}
              </button>
            ))}
          </div>
        )}
      </CardHeader>

      <CardContent className="space-y-4">
        <p className="text-xs text-muted-foreground">
          Rejected outcomes are counterfactual — what would have happened had the setup been taken. They never count
          toward reported accuracy. If both columns read the same, the threshold isn&apos;t selecting anything.
        </p>

        {mixedRuleSets && (
          <p className="rounded-md border border-amber-500/30 bg-amber-500/5 p-3 text-xs text-muted-foreground">
            <span className="font-medium text-foreground">Mixed rule sets.</span> These rows were produced under{" "}
            {report.strategyVersions.length} different strategy versions ({report.strategyVersions.join(", ")}), so the
            numbers below pool results from rules that were not the same. Compare a single version against a single
            version before drawing a conclusion about a tuning change.
          </p>
        )}

        {report.overall.resolved === 0 ? (
          <p className="rounded-md border border-dashed border-border bg-secondary/20 p-3 text-sm text-muted-foreground">
            No resolved outcomes yet. This fills in as signals reach expiry — roughly a day for the first rows,
            a few weeks before the buckets carry enough weight to act on.
          </p>
        ) : (
          <div className="space-y-5">
            {view.slices.map((s) => (
              <SliceTable key={s.key} slice={s} showHeading={view.slices.length > 1} />
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function SliceTable({ slice, showHeading }: { slice: ThresholdCurveSlice; showHeading: boolean }) {
  return (
    <div className="space-y-1.5">
      {showHeading && (
        <div className="flex items-baseline justify-between">
          <h3 className="text-sm font-medium text-foreground">{slice.label}</h3>
          <span className="text-[11px] text-muted-foreground">
            {slice.resolved} resolved
          </span>
        </div>
      )}

      {slice.resolved === 0 ? (
        <p className="text-xs text-muted-foreground">No resolved outcomes in this slice yet.</p>
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
              {slice.buckets.map((b) => (
                <Row key={b.label} bucket={b} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
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
