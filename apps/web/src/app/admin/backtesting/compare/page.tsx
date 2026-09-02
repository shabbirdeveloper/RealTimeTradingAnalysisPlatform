import { getBacktests, type BacktestRow } from "@/lib/backtests";
import { Card, CardContent } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { formatDateTimeUTC } from "@/lib/utils";

export const dynamic = "force-dynamic";

/**
 * Break-even at a typical 80% binary payout. A comparison table without it
 * invites reading the highest number in the column as "good", when the
 * question is whether ANY row clears the bar.
 */
const BREAK_EVEN = 100 / 1.8;

export default async function BacktestComparePage() {
  const runs = (await getBacktests(50)).filter((r) => r.status === "COMPLETED");

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold tracking-tight text-foreground">Run Comparison</h1>
        <p className="text-sm text-muted-foreground">
          Completed backtest runs, side by side. Every figure comes from a real run
          over stored candles — nothing on this page is illustrative.
        </p>
      </div>

      {runs.length === 0 ? (
        <Card className="border-dashed">
          <CardContent className="space-y-3 p-6">
            <p className="text-sm text-muted-foreground">
              No completed backtest runs yet. Start one from{" "}
              <span className="text-foreground">Backtesting</span>, or run{" "}
              <code className="font-mono-tabular text-xs">sweep.py</code> /{" "}
              <code className="font-mono-tabular text-xs">gate_sweep.py</code> against
              stored history.
            </p>
            <p className="text-sm text-muted-foreground">
              This page previously showed a worked example from the spec (XGBoost 91.2%,
              LightGBM 92.0%). Those were illustrative numbers for a model pipeline that
              does not exist yet, and an admin table is the last place they belong — so
              they are gone rather than relabelled.
            </p>
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Run</TableHead>
                  <TableHead>Window</TableHead>
                  <TableHead className="text-right">Min score</TableHead>
                  <TableHead className="text-right">Accepted</TableHead>
                  <TableHead className="text-right">W / L</TableHead>
                  <TableHead className="text-right">Win rate</TableHead>
                  <TableHead>vs break-even</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {runs.map((r) => (
                  <TableRow key={r.id}>
                    <TableCell className="font-medium text-foreground">
                      {r.assetSymbol ?? "all assets"}
                      {r.expiryMinutes !== null && ` · ${r.expiryMinutes}m`}
                      <span className="block text-[10.5px] font-normal text-muted-foreground">
                        {formatDateTimeUTC(r.startDate)}
                      </span>
                    </TableCell>
                    <TableCell className="whitespace-nowrap text-xs text-muted-foreground">
                      {r.startDate.slice(0, 10)} → {r.endDate.slice(0, 10)}
                    </TableCell>
                    <TableCell className="text-right font-mono-tabular">
                      {r.minTechnicalScore ?? "—"}
                    </TableCell>
                    <TableCell className="text-right font-mono-tabular">
                      {r.acceptedSignals ?? "—"}
                    </TableCell>
                    <TableCell className="text-right font-mono-tabular">
                      {r.wins ?? 0} / {r.losses ?? 0}
                    </TableCell>
                    <TableCell className="text-right font-mono-tabular">
                      {r.winRate !== null ? `${r.winRate}%` : "—"}
                    </TableCell>
                    <TableCell>{verdict(r)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}

      <p className="text-xs text-muted-foreground">
        Break-even at an 80% payout is {BREAK_EVEN.toFixed(1)}%. A run below it loses
        money however many signals it produced.
      </p>
    </div>
  );
}

function verdict(run: BacktestRow) {
  const decided = (run.wins ?? 0) + (run.losses ?? 0);
  if (decided === 0) return <span className="text-xs text-muted-foreground">nothing resolved</span>;
  if (decided < 30) {
    return <Badge variant="outline">too few ({decided})</Badge>;
  }
  const rate = run.winRate ?? 0;
  if (rate > BREAK_EVEN) return <Badge>above break-even</Badge>;
  return <Badge variant="destructive">below break-even</Badge>;
}
