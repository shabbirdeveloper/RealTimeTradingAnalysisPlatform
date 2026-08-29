import { getSystemHealth } from "@/lib/admin";
import { Card, CardContent } from "@/components/ui/card";
import { StatusDot } from "@/components/admin/status-dot";
import { formatDateTimeUTC } from "@/lib/utils";

export const dynamic = "force-dynamic";

// Spec section 35's component list. Only the ones this codebase actually
// reports into `system_health` get a real status dot; everything else is
// shown as "Not monitored yet" rather than a fabricated Healthy/Offline
// guess -- see docs/PHASE-STATUS.md for what's real vs not yet built.
const NOT_YET_MONITORED = [
  "Frontend", "API", "Database", "Feature Engine", "Signal Engine",
  "ML Engine", "News API", "Notifications", "WebSockets",
];

export default async function AdminSystemPage() {
  const health = await getSystemHealth();

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold tracking-tight text-foreground">System Health</h1>
        <p className="text-sm text-muted-foreground">Component-level status across the platform.</p>
      </div>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {health.map((c) => {
          const details = c.details as { provider?: string; latency_ms?: number; error?: string };
          return (
            <Card key={c.component}>
              <CardContent className="flex items-center justify-between p-4">
                <div>
                  <p className="text-sm font-medium text-foreground">{c.component}</p>
                  <p className="mt-0.5 text-xs text-muted-foreground">
                    {details.error ? details.error : `Checked ${formatDateTimeUTC(c.lastCheckedAt)}`}
                  </p>
                  {details.latency_ms !== undefined && <p className="mt-0.5 font-mono-tabular text-xs text-muted-foreground">{details.latency_ms}ms</p>}
                </div>
                <StatusDot status={c.status} />
              </CardContent>
            </Card>
          );
        })}
        {NOT_YET_MONITORED.map((name) => (
          <Card key={name}>
            <CardContent className="flex items-center justify-between p-4">
              <div>
                <p className="text-sm font-medium text-foreground">{name}</p>
                <p className="mt-0.5 text-xs text-muted-foreground">No health check reports into this yet</p>
              </div>
              <span className="text-xs font-medium text-muted-foreground">Not monitored</span>
            </CardContent>
          </Card>
        ))}
      </div>
      {health.length === 0 && (
        <p className="text-sm text-muted-foreground">
          No real components have reported health yet — this fills in once the collector runs (market_data.* rows).
        </p>
      )}
    </div>
  );
}
