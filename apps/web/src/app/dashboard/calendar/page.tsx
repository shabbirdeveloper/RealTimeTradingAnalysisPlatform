import { getEconomicEvents, activeBlackoutEvent, BLACKOUT_MINUTES } from "@/lib/calendar";
import { Card, CardContent } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { formatDateTimeUTC, cn } from "@/lib/utils";
import { AlertTriangle, CalendarOff } from "lucide-react";

export const dynamic = "force-dynamic";

const IMPACT_STYLE: Record<string, string> = {
  HIGH: "border-put/30 bg-put-muted text-put-foreground",
  MEDIUM: "border-notrade/30 bg-notrade-muted text-notrade-foreground",
  LOW: "border-border text-muted-foreground",
};

export default async function CalendarPage() {
  const events = await getEconomicEvents();
  const blackout = activeBlackoutEvent(events);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold tracking-tight text-foreground">Economic Calendar</h1>
        <p className="text-sm text-muted-foreground">
          High-impact relevant events automatically pause signal generation for a {BLACKOUT_MINUTES}-minute blackout
          window either side of the release.
        </p>
      </div>

      {events.length === 0 ? (
        <div className="flex items-start gap-2.5 rounded-lg border border-notrade/30 bg-notrade-muted/50 px-4 py-3 text-sm text-notrade-foreground">
          <CalendarOff className="mt-0.5 h-4 w-4 shrink-0" />
          <span>
            <strong className="font-semibold">No economic calendar feed is connected.</strong> This is not an empty
            day — the platform currently has no calendar data at all, so{" "}
            <strong className="font-semibold">high-impact news is not being screened automatically</strong>. Every
            signal carries this warning too. Check an external calendar yourself before trading, especially around
            CPI, NFP, and FOMC releases.
          </span>
        </div>
      ) : (
        blackout && (
          <div className="flex items-center gap-2 rounded-md border border-put/30 bg-put-muted px-4 py-2.5 text-sm text-put-foreground">
            <AlertTriangle className="h-4 w-4 shrink-0" />
            <span>
              <strong className="font-semibold">Signals paused:</strong> {blackout.event} ({blackout.currency})
              inside the blackout window — {formatDateTimeUTC(blackout.dateTime)}.
            </span>
          </div>
        )
      )}

      {events.length > 0 && (
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
      )}
    </div>
  );
}
