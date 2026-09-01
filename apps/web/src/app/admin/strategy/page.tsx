import { getStrategyReport, STRATEGY_DEFAULTS } from "@/lib/admin";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { formatDateTimeUTC, formatExpiry } from "@/lib/utils";

export const dynamic = "force-dynamic";

/**
 * What rules the signal engine is actually running.
 *
 * Read-only on purpose, for now. Editing thresholds is a decision that should
 * be made from the threshold curve on /admin/signals once there is enough
 * resolved history to read it — not from this page, where the numbers sit
 * without the evidence that would justify changing them. The SQL to make a
 * change is shown below so it stays a config edit rather than a code edit.
 */
export default async function AdminStrategyPage() {
  const report = await getStrategyReport();

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold tracking-tight text-foreground">Strategy</h1>
        <p className="text-sm text-muted-foreground">
          Per asset and expiry. An asset with no override row runs the shipped defaults.
        </p>
      </div>

      {!report.ok && (
        <Card>
          <CardContent className="p-4">
            <p className="text-sm text-foreground">Strategy configuration could not be read.</p>
            <p className="mt-1 text-xs text-muted-foreground">{report.error}</p>
            <p className="mt-2 text-xs text-muted-foreground">
              If this reads &ldquo;relation does not exist&rdquo;, migration{" "}
              <code className="font-mono-tabular">20260830000015_strategy_configs</code> has not been applied yet.
              The engine falls back to the shipped defaults until it is, so signals keep generating.
            </p>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle>Shipped defaults</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2 text-sm">
          <Field label="Minimum technical score">{STRATEGY_DEFAULTS.minTechnicalScore}</Field>
          <Field label="Permitted regimes">All ({STRATEGY_DEFAULTS.regimes.length})</Field>
          <Field label="Permitted sessions">All ({STRATEGY_DEFAULTS.sessions.length})</Field>
          <p className="pt-2 text-xs text-muted-foreground">
            These apply to every asset and expiry with no override row, and reproduce the engine&apos;s behaviour
            before per-asset configuration existed. Note that regime and session lists can only <em>narrow</em> what
            the engine does: the hard stand-down on high-volatility and unstable markets sits above this layer, so
            permitting those regimes here does not enable trading in them.
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Overrides ({report.overrides.length})</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          {report.overrides.length === 0 ? (
            <p className="p-4 text-sm text-muted-foreground">
              No overrides. Every asset and expiry is running the shipped defaults above.
            </p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Asset</TableHead>
                  <TableHead>Expiry</TableHead>
                  <TableHead>Min score</TableHead>
                  <TableHead>Regimes</TableHead>
                  <TableHead>Sessions</TableHead>
                  <TableHead>Label</TableHead>
                  <TableHead>Updated</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {report.overrides.map((o) => (
                  <TableRow key={`${o.asset}-${o.expirySeconds}`}>
                    <TableCell className="font-medium text-foreground">{o.asset}</TableCell>
                    <TableCell>{formatExpiry(o.expirySeconds)}</TableCell>
                    <TableCell className="font-mono-tabular">
                      {o.enabled ? o.minTechnicalScore : <Badge variant="destructive">disabled</Badge>}
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {o.allowedRegimes.length === STRATEGY_DEFAULTS.regimes.length
                        ? "all"
                        : o.allowedRegimes.join(", ")}
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {o.allowedSessions.length === STRATEGY_DEFAULTS.sessions.length
                        ? "all"
                        : o.allowedSessions.join(", ")}
                    </TableCell>
                    <TableCell className="font-mono-tabular text-xs">{o.label}</TableCell>
                    <TableCell className="whitespace-nowrap text-xs text-muted-foreground">
                      {o.isDefault ? (
                        <span title="This row sets nothing different from the defaults.">no effect</span>
                      ) : (
                        o.updatedAt && formatDateTimeUTC(o.updatedAt)
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Rule sets seen in stored signals</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 p-4">
          <p className="text-xs text-muted-foreground">
            What the engine actually stamped, not what the table above says it should be. The two can disagree while
            a collector is between config reloads, and the stamped value is the one that describes the stored results.
            Never compare accuracy across two different version strings without saying so — they were produced by
            different rules.
          </p>
          {report.activeVersions.length === 0 ? (
            <p className="text-sm text-muted-foreground">No versioned signals recorded yet.</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Asset</TableHead>
                  <TableHead>Strategy version</TableHead>
                  <TableHead className="text-right">Signals</TableHead>
                  <TableHead>Last seen</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {report.activeVersions.map((v) => (
                  <TableRow key={`${v.asset}-${v.strategyVersion}`}>
                    <TableCell className="font-medium text-foreground">{v.asset}</TableCell>
                    <TableCell className="font-mono-tabular text-xs">{v.strategyVersion}</TableCell>
                    <TableCell className="text-right font-mono-tabular">{v.signals}</TableCell>
                    <TableCell className="whitespace-nowrap text-xs text-muted-foreground">
                      {formatDateTimeUTC(v.lastSeen)}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
          <p className="text-xs text-muted-foreground">
            Counts are over the most recent 5,000 signals, so they show which rule sets are in play — not a complete
            historical total.
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Changing a threshold</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 p-4">
          <p className="text-xs text-muted-foreground">
            Run this against the database. The collector picks the change up within a minute — no redeploy. Every
            signal generated afterwards carries a new version string automatically, so before and after stay
            separable even if the label is left unchanged.
          </p>
          <pre className="overflow-x-auto rounded-md border border-border bg-secondary/20 p-3 text-xs leading-relaxed">
{`-- expiry_seconds, not minutes: 900 = 15m. OTC horizons are 15-180s,
-- which the old minutes column could not express at all.
insert into strategy_configs (asset_id, expiry_seconds, min_technical_score, label)
select id, 900, 84, 'v3-tighter-gold' from assets where symbol = 'XAUUSD'
on conflict (asset_id, expiry_seconds) do update
  set min_technical_score = excluded.min_technical_score,
      label               = excluded.label,
      updated_at          = now();`}
          </pre>
          <p className="text-xs text-muted-foreground">
            Raising a threshold does not discard the setups it excludes: they are still stored as rejected
            opportunities and shadow-resolved, so the threshold curve keeps telling you whether the change was right.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-4 border-b border-border/60 py-1.5 last:border-0">
      <span className="text-muted-foreground">{label}</span>
      <span className="font-mono-tabular text-foreground">{children}</span>
    </div>
  );
}
