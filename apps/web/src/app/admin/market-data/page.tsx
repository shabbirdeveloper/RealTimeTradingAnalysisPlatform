import { ASSET_LIST, ASSET_CONFIGS } from "@/data/assets";
import { ANCHOR_DATE } from "@/data/history";
import { Card, CardContent } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { DataStatusPill, DemoDataBanner } from "@/components/shared/badges";
import { formatDateTimeUTC } from "@/lib/utils";

const ROWS = ASSET_LIST.map((a, i) => ({
  asset: a,
  provider: "Demo Feed Simulator",
  status: "LIVE" as const,
  lastQuote: new Date(ANCHOR_DATE.getTime() - (i + 1) * 4000).toISOString(),
  lastCandle: new Date(ANCHOR_DATE.getTime() - (i + 1) * 60000).toISOString(),
  latencyMs: 180 + i * 40,
  missingCandles: i === 1 ? 2 : 0,
  wsStatus: "Connected",
  apiErrors24h: i === 2 ? 1 : 0,
}));

export default function AdminMarketDataPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold tracking-tight text-foreground">Market Data</h1>
        <p className="text-sm text-muted-foreground">New signal generation is disabled automatically if any feed goes stale.</p>
      </div>
      <DemoDataBanner />
      <Card>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Asset</TableHead>
                <TableHead>Provider</TableHead>
                <TableHead>Connection</TableHead>
                <TableHead>Last quote</TableHead>
                <TableHead>Last candle</TableHead>
                <TableHead>Latency</TableHead>
                <TableHead>Missing candles</TableHead>
                <TableHead>WebSocket</TableHead>
                <TableHead>API errors (24h)</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {ROWS.map((r) => (
                <TableRow key={r.asset}>
                  <TableCell className="font-medium text-foreground">{ASSET_CONFIGS[r.asset].displayName}</TableCell>
                  <TableCell className="text-muted-foreground">{r.provider}</TableCell>
                  <TableCell><DataStatusPill status={r.status} /></TableCell>
                  <TableCell className="whitespace-nowrap text-xs text-muted-foreground">{formatDateTimeUTC(r.lastQuote)}</TableCell>
                  <TableCell className="whitespace-nowrap text-xs text-muted-foreground">{formatDateTimeUTC(r.lastCandle)}</TableCell>
                  <TableCell className="font-mono-tabular">{r.latencyMs}ms</TableCell>
                  <TableCell className={r.missingCandles > 0 ? "text-notrade" : "text-muted-foreground"}>{r.missingCandles}</TableCell>
                  <TableCell className="text-call">{r.wsStatus}</TableCell>
                  <TableCell className={r.apiErrors24h > 0 ? "text-put" : "text-muted-foreground"}>{r.apiErrors24h}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
