import { ECONOMIC_EVENTS, ANCHOR_DATE } from "@/data/history";
import { Card, CardContent } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { DemoDataBanner } from "@/components/shared/badges";
import { formatDateTimeUTC } from "@/lib/utils";
import { AlertTriangle } from "lucide-react";
import { cn } from "@/lib/utils";

const IMPACT_STYLE: Record<string, string> = {
  HIGH: "border-put/30 bg-put-muted text-put-foreground",
  MEDIUM: "border-notrade/30 bg-notrade-muted text-notrade-foreground",
  LOW: "border-border text-muted-foreground",
};

export default function CalendarPage() {
  const events = [...ECONOMIC_EVENTS].sort((a, b) => new Date(a.dateTime).getTime() - new Date(b.dateTime).getTime());
  const nextHighImpact = events.find((e) => e.impact === "HIGH" && new Date(e.dateTime).getTime() - ANCHOR_DATE.getTime() < 3 * 3600000);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold tracking-tight text-foreground">Economic Calendar</h1>
        <p className="text-sm text-muted-foreground">High-impact relevant events automatically pause signal generation for a configurable blackout window.</p>
      </div>

      <DemoDataBanner />

      {nextHighImpact && (
        <div className="flex items-center gap-2 rounded-md border border-put/30 bg-put-muted px-4 py-2.5 text-sm text-put-foreground">
          <AlertTriangle className="h-4 w-4 shrink-0" />
          <span>
            <strong className="font-semibold">Signals paused:</strong> {nextHighImpact.event} ({nextHighImpact.currency}) inside blackout window — {formatDateTimeUTC(nextHighImpact.dateTime)}.
          </span>
        </div>
      )}

      <Card>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Time</TableHead>
                <TableHead>Currency</TableHead>
                <TableHead>Event</TableHead>
                <TableHead>Impact</TableHead>
                <TableHead>Previous</TableHead>
                <TableHead>Forecast</TableHead>
                <TableHead>Actual</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {events.map((e) => (
                <TableRow key={e.id}>
                  <TableCell className="whitespace-nowrap text-xs text-muted-foreground">{formatDateTimeUTC(e.dateTime)}</TableCell>
                  <TableCell className="font-medium">{e.currency}</TableCell>
                  <TableCell>{e.event}</TableCell>
                  <TableCell>
                    <span className={cn("inline-flex items-center rounded-md border px-2 py-0.5 text-[11px] font-semibold", IMPACT_STYLE[e.impact])}>
                      {e.impact}
                    </span>
                  </TableCell>
                  <TableCell className="font-mono-tabular text-muted-foreground">{e.previous ?? "—"}</TableCell>
                  <TableCell className="font-mono-tabular text-muted-foreground">{e.forecast ?? "—"}</TableCell>
                  <TableCell className="font-mono-tabular text-muted-foreground">{e.actual ?? "Pending"}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
