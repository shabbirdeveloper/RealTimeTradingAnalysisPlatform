"use client";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { SideMeter } from "@/components/dashboard/side-meter";
import { useNow } from "@/lib/use-now";
import { cn, formatRelative } from "@/lib/utils";
import type { EngineDecision, EngineSnapshot } from "@/lib/engine-monitor";
import { Activity, Ban, CheckCircle2, CircleSlash, Clock, Radio } from "lucide-react";

const CATEGORY_LABELS: Array<[string, string]> = [
  ["trend", "Trend"],
  ["structure", "Structure"],
  ["momentum", "Momentum"],
  ["price_action", "Price action"],
  ["levels", "Levels"],
  ["volatility", "Volatility"],
  ["entry_timing", "Entry timing"],
];

const CATEGORY_MAX: Record<string, number> = {
  trend: 20, structure: 20, momentum: 20, price_action: 15,
  levels: 10, volatility: 10, entry_timing: 5,
};

export function EngineMonitor({ snapshot }: { snapshot: EngineSnapshot }) {
  const now = useNow(15_000);

  if (!snapshot.available) {
    return (
      <Card className="border-destructive/40">
        <CardContent className="space-y-1 p-5 text-sm">
          <p className="font-medium text-destructive">The engine&apos;s decisions could not be read.</p>
          <p className="text-muted-foreground">{snapshot.error ?? "Unknown error."}</p>
        </CardContent>
      </Card>
    );
  }

  const { latest, today } = snapshot;

  return (
    <div className="space-y-5">
      {/* ---- what happened today ------------------------------------- */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        <Tile label="Evaluations" value={today.evaluations} icon={<Activity className="h-3.5 w-3.5" />} />
        <Tile label="Signals" value={today.signals} tone="call" icon={<Radio className="h-3.5 w-3.5" />} />
        <Tile label="Declined" value={today.rejections} tone="notrade" icon={<Ban className="h-3.5 w-3.5" />} />
        <Tile label="Won" value={today.won} tone="call" icon={<CheckCircle2 className="h-3.5 w-3.5" />} />
        <Tile label="Lost" value={today.lost} tone="put" icon={<CircleSlash className="h-3.5 w-3.5" />} />
        <Tile label="Pending" value={today.pending} icon={<Clock className="h-3.5 w-3.5" />} />
      </div>

      {today.evaluations === 0 && (
        <Card className="border-dashed">
          <CardContent className="p-5 text-sm text-muted-foreground">
            No evaluation has been recorded since 00:00 UTC. If the collector is
            running, the first row appears within 30 seconds.
          </CardContent>
        </Card>
      )}

      {snapshot.rejectionsHidden && (
        <p className="text-xs text-muted-foreground">
          Declined setups are visible to admins only, so the counts above show
          accepted signals for this account.
        </p>
      )}

      {/* ---- the current read ---------------------------------------- */}
      {latest && <CurrentRead decision={latest} nowMs={now?.getTime()} />}

      {/* ---- what is stopping it ------------------------------------- */}
      {snapshot.topBlockers.length > 0 && (
        <section className="space-y-2">
          <h2 className="text-sm font-semibold text-foreground">What stopped the rest</h2>
          <p className="text-xs text-muted-foreground">
            The first gate each declined cycle failed, today, most frequent first.
            Numbers are grouped, so &ldquo;score N below the N floor&rdquo; covers every score.
          </p>
          <Card>
            <CardContent className="divide-y divide-border p-0">
              {snapshot.topBlockers.map((b) => (
                <div key={b.reason} className="flex items-center justify-between gap-3 px-4 py-2.5">
                  <span className="text-xs text-muted-foreground">{b.reason}</span>
                  <span className="font-mono-tabular text-xs font-semibold text-foreground">{b.count}</span>
                </div>
              ))}
            </CardContent>
          </Card>
        </section>
      )}

      {/* ---- the tape ------------------------------------------------ */}
      <section className="space-y-2">
        <h2 className="text-sm font-semibold text-foreground">Recent cycles</h2>
        <Card>
          <CardContent className="divide-y divide-border p-0">
            {snapshot.recent.map((d) => (
              <CycleRow key={d.id} decision={d} nowMs={now?.getTime()} />
            ))}
            {snapshot.recent.length === 0 && (
              <p className="p-4 text-sm text-muted-foreground">Nothing recorded yet.</p>
            )}
          </CardContent>
        </Card>
      </section>
    </div>
  );
}

function CurrentRead({ decision, nowMs }: { decision: EngineDecision; nowMs?: number }) {
  const isSignal = decision.direction !== "NO_TRADE" && decision.status !== "REJECTED";
  return (
    <Card className={cn(isSignal && "border-primary/40")}>
      <CardContent className="space-y-4 p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-sm font-semibold text-foreground">
              {decision.symbol} · latest read
            </p>
            <p className="text-xs text-muted-foreground">
              {formatRelative(decision.generatedAt, nowMs)}
              {decision.expirySeconds ? ` · ${Math.round(decision.expirySeconds / 60)} min expiry` : ""}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {decision.feedStatus && (
              <Badge variant="outline" className={cn(decision.feedStatus !== "HEALTHY" && "text-destructive")}>
                Feed {decision.feedStatus.toLowerCase()}
              </Badge>
            )}
            {decision.regime && <Badge variant="outline" className="capitalize">{decision.regime.replace(/_/g, " ").toLowerCase()}</Badge>}
          </div>
        </div>

        {decision.regimeReason && (
          <p className="text-xs text-muted-foreground">{decision.regimeReason}</p>
        )}

        {decision.callScore !== null && decision.putScore !== null && (
          <SideMeter call={decision.callScore} put={decision.putScore} />
        )}

        <div className="grid gap-4 sm:grid-cols-2">
          <CategoryBreakdown title="CALL" tone="call" scores={decision.callCategories} />
          <CategoryBreakdown title="PUT" tone="put" scores={decision.putCategories} />
        </div>

        {decision.rejectionReasons.length > 0 && (
          <div className="space-y-1 rounded-md border border-dashed border-border bg-secondary/30 p-3">
            <p className="text-[10.5px] font-medium uppercase tracking-wider text-muted-foreground">
              Declined because
            </p>
            {decision.rejectionReasons.map((r) => (
              <p key={r} className="text-xs text-foreground">{r}</p>
            ))}
          </div>
        )}

        {decision.reasons.length > 0 && (
          <ul className="space-y-1">
            {decision.reasons.slice(0, 8).map((r) => (
              <li key={r} className="text-xs text-muted-foreground">· {r}</li>
            ))}
          </ul>
        )}

        {decision.warnings.length > 0 && (
          <ul className="space-y-1">
            {decision.warnings.map((w) => (
              <li key={w} className="text-xs text-notrade">! {w}</li>
            ))}
          </ul>
        )}

        {decision.strategy && (
          <p className="text-[10.5px] uppercase tracking-wider text-muted-foreground">
            Strategy · {decision.strategy.replace(/_/g, " ")}
          </p>
        )}
      </CardContent>
    </Card>
  );
}

function CategoryBreakdown({
  title, tone, scores,
}: {
  title: string;
  tone: "call" | "put";
  scores: Record<string, number> | null;
}) {
  if (!scores) return null;
  return (
    <div className="space-y-1.5">
      <p className={cn("text-[10.5px] font-semibold uppercase tracking-wider", tone === "call" ? "text-call" : "text-put")}>
        {title} evidence
      </p>
      {CATEGORY_LABELS.map(([key, label]) => {
        const value = scores[key] ?? 0;
        const max = CATEGORY_MAX[key] ?? 20;
        return (
          <div key={key} className="flex items-center gap-2">
            <span className="w-20 shrink-0 text-[10px] text-muted-foreground">{label}</span>
            <div className="h-1 flex-1 overflow-hidden rounded-full bg-secondary">
              <div
                className={cn("h-full rounded-full", tone === "call" ? "bg-call" : "bg-put")}
                style={{ width: `${Math.min(100, (value / max) * 100)}%` }}
              />
            </div>
            <span className="w-8 shrink-0 text-right font-mono-tabular text-[10px] text-muted-foreground">
              {value}/{max}
            </span>
          </div>
        );
      })}
    </div>
  );
}

function CycleRow({ decision, nowMs }: { decision: EngineDecision; nowMs?: number }) {
  const declined = decision.status === "REJECTED" || decision.status === "CANDIDATE";
  const note = declined
    ? decision.rejectionReasons[0] ?? "declined"
    : decision.reasons[0] ?? decision.status.toLowerCase();

  return (
    <div className="flex items-center gap-3 px-4 py-2.5">
      <span className="w-16 shrink-0 font-mono-tabular text-[11px] text-muted-foreground">
        {formatRelative(decision.generatedAt, nowMs)}
      </span>
      <span
        className={cn(
          "w-16 shrink-0 text-[11px] font-semibold",
          declined ? "text-notrade" : decision.direction === "CALL" ? "text-call" : "text-put"
        )}
      >
        {declined ? "NO TRADE" : decision.direction}
      </span>
      <span className="w-20 shrink-0 font-mono-tabular text-[11px] text-muted-foreground">
        {decision.callScore ?? "—"} / {decision.putScore ?? "—"}
      </span>
      <span className="min-w-0 flex-1 truncate text-[11px] text-muted-foreground">{note}</span>
      {decision.result && (
        <span
          className={cn(
            "shrink-0 text-[11px] font-semibold",
            decision.result === "WON" ? "text-call" : decision.result === "LOST" ? "text-put" : "text-muted-foreground"
          )}
        >
          {decision.result}
        </span>
      )}
    </div>
  );
}

function Tile({
  label, value, tone, icon,
}: {
  label: string;
  value: number;
  tone?: "call" | "put" | "notrade";
  icon?: React.ReactNode;
}) {
  return (
    <Card>
      <CardContent className="space-y-1 p-3.5">
        <p className="flex items-center gap-1.5 text-[10.5px] font-medium uppercase tracking-wider text-muted-foreground">
          {icon}
          {label}
        </p>
        <p
          className={cn(
            "font-mono-tabular text-xl font-semibold",
            tone === "call" ? "text-call" : tone === "put" ? "text-put" : tone === "notrade" ? "text-notrade" : "text-foreground"
          )}
        >
          {value}
        </p>
      </CardContent>
    </Card>
  );
}
