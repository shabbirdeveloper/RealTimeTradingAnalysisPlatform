import { ECONOMIC_EVENTS } from "@/data/history";
import { Card, CardContent } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { DemoDataBanner } from "@/components/shared/badges";
import { formatDateTimeUTC } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";

export default function AdminNewsPage() {
  const events = [...ECONOMIC_EVENTS].sort((a, b) => new Date(a.dateTime).getTime() - new Date(b.dateTime).getTime());
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold tracking-tight text-foreground">News Feed</h1>
        <p className="text-sm text-muted-foreground">Source events for the blackout window applied to the Calendar page and Signal Engine.</p>
      </div>
      <DemoDataBanner />
      <Card>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Time</TableHead>
                <TableHead>Currency</TableHead>
                <TableHead>Event</TableHead>
                <TableHead>Impact</TableHead>
                <TableHead>Affects</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {events.map((e) => (
                <TableRow key={e.id}>
                  <TableCell className="whitespace-nowrap text-xs text-muted-foreground">{formatDateTimeUTC(e.dateTime)}</TableCell>
                  <TableCell>{e.currency}</TableCell>
                  <TableCell>{e.event}</TableCell>
                  <TableCell><Badge variant={e.impact === "HIGH" ? "put" : e.impact === "MEDIUM" ? "notrade" : "outline"}>{e.impact}</Badge></TableCell>
                  <TableCell className="text-xs text-muted-foreground">{e.affectsAssets.join(", ")}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
