import { getEconomicEvents } from "@/lib/calendar";
import { Card, CardContent } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { formatDateTimeUTC } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { CalendarOff } from "lucide-react";
import type { AssetSymbol } from "@/types";

export const dynamic = "force-dynamic";

// Mirrors ASSET_CURRENCIES in apps/api/app/news/blackout.py. Gold is quoted
// in USD, so XAUUSD is USD-sensitive even though "XAU" is not a currency.
const CURRENCY_AFFECTS: Record<string, AssetSymbol[]> = {
  USD: ["XAUUSD", "EURUSD", "GBPUSD"],
  EUR: ["EURUSD"],
  GBP: ["GBPUSD"],
};

export default async function AdminNewsPage() {
  const events = await getEconomicEvents(2, 14);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold tracking-tight text-foreground">News Feed</h1>
        <p className="text-sm text-muted-foreground">Source events for the blackout window applied to the Calendar page and the signal engine.</p>
      </div>

      {events.length === 0 ? (
        <div className="flex items-start gap-2.5 rounded-lg border border-notrade/30 bg-notrade-muted/50 px-4 py-3 text-sm text-notrade-foreground">
          <CalendarOff className="mt-0.5 h-4 w-4 shrink-0" />
          <span>
            <strong className="font-semibold">No calendar provider is configured</strong>, so the{" "}
            <code className="rounded bg-secondary px-1 py-0.5">economic_events</code> table is empty and the news
            filter has nothing to act on. The blackout logic itself is built and tested — it just needs a feed. See{" "}
            <code className="rounded bg-secondary px-1 py-0.5">apps/api/app/news/base.py</code> for what implementing
            one involves.
          </span>
        </div>
      ) : (
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
                  <TableHead>Source</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {events.map((e) => (
                  <TableRow key={e.id}>
                    <TableCell className="whitespace-nowrap text-xs text-muted-foreground">{formatDateTimeUTC(e.dateTime)}</TableCell>
                    <TableCell>{e.currency}</TableCell>
                    <TableCell>{e.event}</TableCell>
                    <TableCell>
                      <Badge variant={e.impact === "HIGH" ? "put" : e.impact === "MEDIUM" ? "notrade" : "outline"}>{e.impact}</Badge>
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {(CURRENCY_AFFECTS[e.currency] ?? []).join(", ") || "—"}
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">{e.source ?? "—"}</TableCell>
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
