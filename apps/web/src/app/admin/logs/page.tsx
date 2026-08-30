import { getAuditLogs } from "@/lib/admin";
import { Card, CardContent } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { formatDateTimeUTC } from "@/lib/utils";

export const dynamic = "force-dynamic";

/** Human labels for the `domain.verb` action names written by apps/api. */
const ACTION_LABEL: Record<string, string> = {
  "backtest.create": "Backtest started",
  "backtest.complete": "Backtest completed",
  "backtest.failed": "Backtest failed",
  "market_data.failed": "Market data fetch failed",
  "signals.resolved": "Signals resolved",
  "analysis.failed": "Analysis cycle failed",
};

function isFailure(action: string): boolean {
  return action.endsWith(".failed");
}

function describe(metadata: Record<string, unknown>): string {
  const entries = Object.entries(metadata).filter(([, v]) => v !== null && v !== undefined);
  if (entries.length === 0) return "—";
  return entries.map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join(", ") : String(v)}`).join(" · ");
}

export default async function AdminLogsPage() {
  const logs = await getAuditLogs();

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold tracking-tight text-foreground">Audit Logs</h1>
        <p className="text-sm text-muted-foreground">
          Operational and administrative events, most recent first. Individual signals are not logged here — they are
          already stored in full, including rejected ones, under Signals.
        </p>
      </div>

      {logs.length === 0 ? (
        <Card>
          <CardContent className="p-5 text-sm text-muted-foreground">
            No audit entries yet. These are written by the signal-engine service as it runs — backtests, market-data
            failures, and signal resolution batches.
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Time</TableHead>
                  <TableHead>Actor</TableHead>
                  <TableHead>Action</TableHead>
                  <TableHead>Target</TableHead>
                  <TableHead>Detail</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {logs.map((l) => (
                  <TableRow key={l.id}>
                    <TableCell className="whitespace-nowrap text-xs text-muted-foreground">
                      {formatDateTimeUTC(l.createdAt)}
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">{l.actorLabel}</TableCell>
                    <TableCell>
                      <Badge variant={isFailure(l.action) ? "put" : "outline"}>
                        {ACTION_LABEL[l.action] ?? l.action}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {l.targetTable ? `${l.targetTable}${l.targetId ? ` · ${l.targetId}` : ""}` : "—"}
                    </TableCell>
                    <TableCell className="max-w-md truncate text-xs text-muted-foreground" title={describe(l.metadata)}>
                      {describe(l.metadata)}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
