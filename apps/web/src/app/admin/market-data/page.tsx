import { ASSET_LIST, ASSET_CONFIGS } from "@/data/assets";
import { getSystemHealth } from "@/lib/admin";
import { getAssetPriceSnapshots } from "@/lib/market-data";
import { Card, CardContent } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { DataStatusPill } from "@/components/shared/badges";
import { formatDateTimeUTC } from "@/lib/utils";

export const dynamic = "force-dynamic";

export default async function AdminMarketDataPage() {
  const [health, snapshots] = await Promise.all([getSystemHealth(), getAssetPriceSnapshots()]);
  const healthByComponent = new Map(health.map((h) => [h.component, h]));

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold tracking-tight text-foreground">Market Data</h1>
        <p className="text-sm text-muted-foreground">New signal generation is disabled automatically if any feed goes stale.</p>
      </div>
      <Card>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Asset</TableHead>
                <TableHead>Provider</TableHead>
                <TableHead>Connection</TableHead>
                <TableHead>Last checked</TableHead>
                <TableHead>Last candle</TableHead>
                <TableHead>Latency</TableHead>
                <TableHead>Missing candles</TableHead>
                <TableHead>WebSocket / Realtime</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {ASSET_LIST.map((asset) => {
                const h = healthByComponent.get(`market_data.${asset}`);
                const snapshot = snapshots[asset];
                const details = (h?.details ?? {}) as { provider?: string; latency_ms?: number; error?: string };
                return (
                  <TableRow key={asset}>
                    <TableCell className="font-medium text-foreground">{ASSET_CONFIGS[asset].displayName}</TableCell>
                    <TableCell className="text-muted-foreground">{details.provider ?? "—"}</TableCell>
                    <TableCell>
                      {h ? <DataStatusPill status={h.status === "Healthy" ? "LIVE" : h.status === "Warning" ? "DELAYED" : "OFFLINE"} /> : <span className="text-xs text-muted-foreground">Not reported yet</span>}
                    </TableCell>
                    <TableCell className="whitespace-nowrap text-xs text-muted-foreground">{h ? formatDateTimeUTC(h.lastCheckedAt) : "—"}</TableCell>
                    <TableCell className="whitespace-nowrap text-xs text-muted-foreground">{snapshot ? formatDateTimeUTC(snapshot.lastUpdated) : "—"}</TableCell>
                    <TableCell className="font-mono-tabular">{details.latency_ms !== undefined ? `${details.latency_ms}ms` : "—"}</TableCell>
                    <TableCell className="text-xs text-muted-foreground">Not tracked yet</TableCell>
                    <TableCell className="text-xs text-muted-foreground">No custom WebSocket — Supabase Realtime not wired to this page yet</TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
      <p className="text-xs text-muted-foreground">
        &quot;Missing candles&quot; and API-error counts aren&apos;t tracked yet by the collector — shown honestly as
        not tracked rather than a fabricated zero that would imply monitoring exists.
      </p>
    </div>
  );
}
