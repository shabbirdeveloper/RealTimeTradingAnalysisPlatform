import { getBacktests, type BacktestRow } from "@/lib/backtests";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { formatDateTimeUTC, formatPercent } from "@/lib/utils";
import { AlertTriangle } from "lucide-react";
import type { PerformanceBucket } from "@/types";

export const dynamic = "force-dynamic";

export default async function AdminBacktestingPage() {
  const backtests = await getBacktests();

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold tracking-tight text-foreground">Backtesting</h1>
        <p className="text-sm text-muted-foreground">
          Replays the real signal engine over stored candle history — no look-ahead, no future data in feature
          calculation.
        </p>
      </div>

      <div className="flex items-start gap-2.5 rounded-lg border border-notrade/20 bg-notrade-muted/40 px-3.5 py-2 text-xs text-notrade-foreground/90">
        <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-notrade" />
        <span>
          Runs are started from the signal-engine service, not this page —{" "}
          <code className="rounded bg-secondary px-1 py-0.5">POST /admin/backtests</code> on{" "}
          <code className="rounded bg-secondary px-1 py-0.5">apps/api</code> (needs the{" "}
          <code className="rounded bg-secondary px-1 py-0.5">X-Admin-Api-Key</code> header). A backtest can only
          cover candle history that has actually been collected, so results over a short history are a smoke test of
          the rules, <strong className="font-semibold">not evidence of accuracy</strong>.
        </span>
      </div>

      {backtests.length === 0 ? (
        <Card>
          <CardContent className="p-5 text-sm text-muted-foreground">
            No backtests have been run yet. Start one against the signal-engine service, then refresh this page.
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-4">
          {backtests.map((b) => (
            <BacktestCard key={b.id} backtest={b} />
          ))}
        </div>
      )}
    </div>
  );
}

function BacktestCard({ backtest: b }: { backtest: BacktestRow }) {
  const statusVariant =
    b.status === "COMPLETED" ? "call" : b.status === "FAILED" ? "put" : "notrade";

  return (
    <Card>
      <CardHeader className="flex-row flex-wrap items-center justify-between gap-2 space-y-0">
        <div>
          <CardTitle className="text-base">
            {b.assetSymbol ?? "All assets"} · {b.startDate} → {b.endDate}
          </CardTitle>
          <p className="mt-0.5 text-xs text-muted-foreground">
            Min technical score {b.minTechnicalScore ?? "—"}
            {b.expiryMinutes ? ` · ${b.expiryMinutes}m expiry` : " · all expiries"}
            {b.sessionFilter ? ` · ${b.sessionFilter}` : ""}
            {b.regimeFilter ? ` · ${b.regimeFilter}` : ""}
            {" · run "}
            {formatDateTimeUTC(b.createdAt)}
          </p>
        </div>
        <Badge variant={statusVariant}>{b.status}</Badge>
      </CardHeader>
      <CardContent className="space-y-4">
        {b.message && (
          <p
            className={`rounded-md border border-dashed p-3 text-xs ${
              b.status === "FAILED" ? "border-put/40 text-put" : "border-border bg-secondary/30 text-muted-foreground"
            }`}
          >
            {b.message}
          </p>
        )}

        {b.status === "COMPLETED" && (
          <>
            <div className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-7">
              <Stat label="Opportunities" value={String(b.totalOpportunities ?? 0)} />
              <Stat label="Accepted" value={String(b.acceptedSignals ?? 0)} />
              <Stat label="Rejected" value={String(b.rejectedSignals ?? 0)} />
              <Stat label="Coverage" value={formatPercent(b.signalCoverage ?? 0)} />
              <Stat label="Wins / losses" value={`${b.wins ?? 0} / ${b.losses ?? 0}`} />
              <Stat label="Win rate" value={formatPercent(b.winRate ?? 0)} />
              <Stat label="Max streaks" value={`W${b.maxWinStreak ?? 0} / L${b.maxLossStreak ?? 0}`} />
            </div>

            <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
              <Breakdown title="By asset" rows={b.byPair} />
              <Breakdown title="By expiry" rows={b.byExpiry} />
              <Breakdown title="By session" rows={b.bySession} />
              <Breakdown title="By regime" rows={b.byRegime} />
              <Breakdown title="By technical score" rows={b.byScoreBucket} />
            </div>
          </>
        )}

        {(b.status === "PENDING" || b.status === "RUNNING") && (
          <p className="text-sm text-muted-foreground">
            {b.status === "PENDING" ? "Queued." : "Replaying history…"} Refresh to check progress.
          </p>
        )}
      </CardContent>
    </Card>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-border p-3">
      <p className="text-[10.5px] uppercase tracking-wide text-muted-foreground">{label}</p>
      <p className="font-mono-tabular text-sm font-semibold text-foreground">{value}</p>
    </div>
  );
}

function Breakdown({ title, rows }: { title: string; rows: PerformanceBucket[] }) {
  return (
    <div className="rounded-md border border-border p-3">
      <p className="mb-2 text-xs font-semibold text-foreground">{title}</p>
      {rows.length === 0 ? (
        <p className="text-xs text-muted-foreground">No accepted signals to break down.</p>
      ) : (
        <div className="space-y-1.5">
          {rows.map((r) => (
            <div key={r.label} className="flex items-center justify-between text-xs">
              <span className="text-foreground">{r.label}</span>
              <span className="font-mono-tabular text-muted-foreground">
                {r.signals} sig · {r.wins}W/{r.losses}L · {formatPercent(r.accuracy)}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
