import { Card, CardContent } from "@/components/ui/card";
import { getAdminOverview } from "@/lib/admin";
import { formatDateTimeUTC, formatRelative, isCheckStale } from "@/lib/utils";
import Link from "next/link";
import { Users, CreditCard, Radio, Award, Target, Filter } from "lucide-react";
import { StatusDot } from "@/components/admin/status-dot";
import { cn } from "@/lib/utils";

export const dynamic = "force-dynamic";

export default async function AdminOverviewPage() {
  const o = await getAdminOverview();
  const feedStale = isCheckStale(o.newestCandleAt, Date.now(), 30);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold tracking-tight text-foreground">Overview</h1>
        <p className="text-sm text-muted-foreground">
          Platform status, read from the database. Counts marked{" "}
          <span className="font-medium text-foreground">Not tracked</span> are ones the
          platform genuinely cannot answer yet.
        </p>
      </div>

      {(o.pendingApprovals ?? 0) > 0 && (
        <Link
          href="/admin/users"
          className="block rounded-lg border border-notrade/25 bg-notrade-muted/40 px-3.5 py-2 text-xs text-notrade-foreground/90 hover:border-notrade/50"
        >
          <strong className="font-semibold">
            {o.pendingApprovals} {o.pendingApprovals === 1 ? "account is" : "accounts are"} waiting for approval.
          </strong>{" "}
          Review them in Users →
        </Link>
      )}

      {o.usersError && (
        <div className="rounded-lg border border-notrade/25 bg-notrade-muted/40 px-3.5 py-2 text-xs text-notrade-foreground/90">
          User counts unavailable: {o.usersError}
        </div>
      )}

      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        <Tile icon={Users} label="Total users" value={fmt(o.totalUsers)} />
        <Tile icon={CreditCard} label="Subscribers" value={fmt(o.subscribers)} />
        <Tile
          icon={Radio}
          label="Signals today"
          value={String(o.signalsToday)}
          sub={`${o.decisionsToday} decisions`}
        />
        <Tile icon={Award} label="A++ today" value={String(o.aPlusPlusToday)} tone="gold" />
        <Tile icon={Filter} label="Rejected today" value={String(o.rejectedToday)} />
        <Tile
          icon={Target}
          label="Accuracy"
          value={o.accuracy === null ? "No data" : `${o.accuracy}%`}
          sub={o.resolvedTotal > 0 ? `${o.wins}W / ${o.losses}L` : "nothing resolved yet"}
        />
      </div>

      <Card>
        <CardContent className="space-y-4 p-5">
          <div className="flex items-baseline justify-between">
            <h2 className="text-sm font-semibold text-foreground">Components</h2>
            <span className={cn("text-xs", feedStale ? "text-destructive" : "text-muted-foreground")}>
              {o.newestCandleAt
                ? `newest candle ${formatRelative(o.newestCandleAt)} (${formatDateTimeUTC(o.newestCandleAt)})`
                : "no candles stored"}
            </span>
          </div>

          {o.components.length === 0 ? (
            /* An empty health table is itself a finding: the collector writes
               these rows every cycle, so nothing here means nothing ran. */
            <p className="rounded-md border border-dashed border-border bg-secondary/30 p-3 text-xs text-muted-foreground">
              No component has reported health yet. The collector writes a row
              every poll cycle, so an empty table means it has not completed one
              since the database was set up.
            </p>
          ) : (
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
              {o.components.map((c) => (
                <div key={c.component} className="rounded-md border border-border p-3">
                  <div className="flex items-center justify-between">
                    <span className="truncate text-sm text-foreground">{c.component}</span>
                    <StatusDot status={c.status} />
                  </div>
                  <p className="mt-1 text-[10.5px] text-muted-foreground">
                    {formatRelative(c.lastCheckedAt)}
                  </p>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

/** "Not tracked" rather than 0 -- a confident zero for something never
 *  measured is the same class of lie as an invented number. */
function fmt(value: number | null): string {
  return value === null ? "Not tracked" : value.toLocaleString();
}

function Tile({
  icon: Icon, label, value, sub, tone,
}: {
  icon: typeof Users; label: string; value: string; sub?: string; tone?: "gold";
}) {
  return (
    <Card className="card-premium-hover">
      <CardContent className="p-4">
        <span
          className={cn(
            "mb-2.5 flex h-9 w-9 items-center justify-center rounded-lg ring-1 ring-inset",
            tone === "gold"
              ? "bg-gradient-to-br from-aplusplus/25 to-aplusplus/5 text-aplusplus ring-aplusplus/25"
              : "bg-gradient-to-br from-primary/20 to-primary/5 text-primary ring-primary/20"
          )}
        >
          <Icon className="h-4 w-4" />
        </span>
        <p className="text-[10.5px] font-medium uppercase tracking-wider text-muted-foreground">{label}</p>
        <p className="font-mono-tabular text-lg font-semibold text-foreground">{value}</p>
        {sub && <p className="mt-0.5 text-[10.5px] text-muted-foreground">{sub}</p>}
      </CardContent>
    </Card>
  );
}
