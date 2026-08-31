import { ASSET_LIST, ASSET_CONFIGS } from "@/data/assets";
import { getSystemHealth } from "@/lib/admin";
import { getAssetPriceSnapshots } from "@/lib/market-data";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { DataStatusPill } from "@/components/shared/badges";
import { formatDateTimeUTC } from "@/lib/utils";

export const dynamic = "force-dynamic";

/** What the collector records in system_health.details on each poll. Every
 *  field is optional: a collector that hasn't been restarted since these were
 *  added reports the older shape, and a missing field must read as "not
 *  reported" rather than a confident zero. */
interface FeedDetails {
  provider?: string;
  latency_ms?: number;
  error?: string;
  forming_bars_dropped?: number;
  future_bars_dropped?: number;
  retries?: number;
  rate_limited?: boolean;
  recovered_from?: string;
}

function count(n: number | undefined) {
  return n === undefined ? <span className="text-muted-foreground">—</span> : <>{n}</>;
}

export default async function AdminMarketDataPage() {
  const [health, snapshots] = await Promise.all([getSystemHealth(), getAssetPriceSnapshots()]);
  const healthByComponent = new Map(health.map((h) => [h.component, h]));

  const rows = ASSET_LIST.map((asset) => ({
    asset,
    health: healthByComponent.get(`market_data.${asset}`),
    snapshot: snapshots[asset],
    details: (healthByComponent.get(`market_data.${asset}`)?.details ?? {}) as FeedDetails,
  }));

  const reporting = rows.filter((r) => r.details.forming_bars_dropped !== undefined);
  const droppingPartials = reporting.filter((r) => (r.details.forming_bars_dropped ?? 0) > 0);
  const anyRateLimited = rows.some((r) => r.details.rate_limited);
  const anyFutureBars = rows.some((r) => (r.details.future_bars_dropped ?? 0) > 0);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold tracking-tight text-foreground">Market Data</h1>
        <p className="text-sm text-muted-foreground">
          New signal generation is disabled automatically if any feed goes stale.
        </p>
      </div>

      {anyFutureBars && (
        <Card className="border-put/40">
          <CardContent className="p-4">
            <p className="text-sm font-medium text-put">Candles with a future open time were rejected.</p>
            <p className="mt-1 text-xs text-muted-foreground">
              This is not a partial bar — it is a bar that cannot exist yet. Either the provider&apos;s clock, this
              server&apos;s clock, or the timezone handling is wrong. Until that is explained, treat this asset&apos;s
              stored history as suspect.
            </p>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Asset</TableHead>
                <TableHead>Provider</TableHead>
                <TableHead>Connection</TableHead>
                <TableHead>Last checked</TableHead>
                <TableHead>Last closed candle</TableHead>
                <TableHead>Latency</TableHead>
                <TableHead className="text-right">Partial bars dropped</TableHead>
                <TableHead className="text-right">Retries</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map(({ asset, health: h, snapshot, details }) => (
                <TableRow key={asset}>
                  <TableCell className="font-medium text-foreground">{ASSET_CONFIGS[asset].displayName}</TableCell>
                  <TableCell className="text-muted-foreground">{details.provider ?? "—"}</TableCell>
                  <TableCell>
                    {h ? (
                      <DataStatusPill
                        status={h.status === "Healthy" ? "LIVE" : h.status === "Warning" ? "DELAYED" : "OFFLINE"}
                      />
                    ) : (
                      <span className="text-xs text-muted-foreground">Not reported yet</span>
                    )}
                  </TableCell>
                  <TableCell className="whitespace-nowrap text-xs text-muted-foreground">
                    {h ? formatDateTimeUTC(h.lastCheckedAt) : "—"}
                  </TableCell>
                  <TableCell className="whitespace-nowrap text-xs text-muted-foreground">
                    {snapshot ? formatDateTimeUTC(snapshot.lastUpdated) : "—"}
                  </TableCell>
                  <TableCell className="font-mono-tabular">
                    {details.latency_ms !== undefined ? `${details.latency_ms}ms` : "—"}
                  </TableCell>
                  <TableCell className="text-right font-mono-tabular">
                    {count(details.forming_bars_dropped)}
                    {(details.future_bars_dropped ?? 0) > 0 && (
                      <span className="ml-1.5 text-[11px] text-put">+{details.future_bars_dropped} future</span>
                    )}
                  </TableCell>
                  <TableCell className="text-right font-mono-tabular">
                    {count(details.retries)}
                    {details.rate_limited && (
                      <span className="ml-1.5 text-[11px] text-amber-500">rate&nbsp;limited</span>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Does this feed include the in-progress bar?</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2 p-4 text-xs text-muted-foreground">
          <p>
            The provider&apos;s documentation doesn&apos;t say, so the collector filters out any bar whose window
            hasn&apos;t closed and counts what it dropped. The count above is the answer, measured rather than assumed.
          </p>
          {reporting.length === 0 ? (
            <p>
              No poll has reported this yet. It appears after the collector next runs — if the counts stay blank after
              that, the running collector predates the filter and needs a restart.
            </p>
          ) : droppingPartials.length > 0 ? (
            <p className="text-foreground">
              Yes — a partial bar is being dropped on {droppingPartials.length} of {reporting.length} feeds. Without
              this filter those bars would have been stored as finished candles, and every indicator and backtest built
              on them would have been quietly wrong.
            </p>
          ) : (
            <p className="text-foreground">
              Not so far — every bar returned had already closed. The filter is a no-op here, which is the outcome you
              want: correctness that doesn&apos;t depend on the provider&apos;s behaviour staying the same.
            </p>
          )}
          {anyRateLimited && (
            <p>
              A rate limit was hit on the most recent poll. Twelve Data&apos;s free tier allows 8 credits/minute and
              800/day; five assets at the current interval already spend most of the daily budget, so sustained rate
              limiting means the poll interval needs to go up, not the retry count.
            </p>
          )}
        </CardContent>
      </Card>

      <p className="text-xs text-muted-foreground">
        Gap detection (counting candles the provider skipped entirely) still isn&apos;t tracked — shown as absent
        rather than a fabricated zero that would imply monitoring exists. Retries and dropped-bar counts describe the
        most recent poll for each asset, not a running total.
      </p>
    </div>
  );
}
