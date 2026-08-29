import { Card, CardContent } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { DemoDataBanner } from "@/components/shared/badges";
import { ANCHOR_DATE } from "@/data/history";
import { formatDateTimeUTC } from "@/lib/utils";

const LOGS = [
  { time: new Date(ANCHOR_DATE.getTime() - 3 * 60000).toISOString(), actor: "system", action: "MODEL_ACTIVATED", detail: "xauusd-30m v1.4.2 activated" },
  { time: new Date(ANCHOR_DATE.getTime() - 25 * 60000).toISOString(), actor: "admin@northfxtrade.com", actorLabel: "Admin", action: "BACKTEST_RUN", detail: "GBPUSD 60m, min confidence 80%" },
  { time: new Date(ANCHOR_DATE.getTime() - 90 * 60000).toISOString(), actor: "system", action: "NEWS_BLACKOUT_START", detail: "US NFP high-impact window" },
  { time: new Date(ANCHOR_DATE.getTime() - 150 * 60000).toISOString(), actor: "system", action: "SIGNAL_REJECTED", detail: "EURUSD candidate below meta-model threshold" },
  { time: new Date(ANCHOR_DATE.getTime() - 240 * 60000).toISOString(), actor: "admin@northfxtrade.com", actorLabel: "Admin", action: "USER_ROLE_CHANGED", detail: "priya@example.com → User" },
];

export default function AdminLogsPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold tracking-tight text-foreground">Audit Logs</h1>
        <p className="text-sm text-muted-foreground">System and admin actions, most recent first.</p>
      </div>
      <DemoDataBanner />
      <Card>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Time</TableHead>
                <TableHead>Actor</TableHead>
                <TableHead>Action</TableHead>
                <TableHead>Detail</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {LOGS.map((l, i) => (
                <TableRow key={i}>
                  <TableCell className="whitespace-nowrap text-xs text-muted-foreground">{formatDateTimeUTC(l.time)}</TableCell>
                  <TableCell className="text-muted-foreground">{l.actorLabel ?? l.actor}</TableCell>
                  <TableCell className="font-mono-tabular text-xs">{l.action}</TableCell>
                  <TableCell className="text-sm text-muted-foreground">{l.detail}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
