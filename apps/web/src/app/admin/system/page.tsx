import { SYSTEM_HEALTH } from "@/data/history";
import { Card, CardContent } from "@/components/ui/card";
import { DemoDataBanner } from "@/components/shared/badges";
import { StatusDot } from "@/components/admin/status-dot";

export default function AdminSystemPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold tracking-tight text-foreground">System Health</h1>
        <p className="text-sm text-muted-foreground">Component-level status across the platform.</p>
      </div>
      <DemoDataBanner />
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {SYSTEM_HEALTH.map((c) => (
          <Card key={c.name}>
            <CardContent className="flex items-center justify-between p-4">
              <div>
                <p className="text-sm font-medium text-foreground">{c.name}</p>
                {c.detail && <p className="mt-0.5 text-xs text-muted-foreground">{c.detail}</p>}
                {c.latencyMs !== undefined && <p className="mt-0.5 font-mono-tabular text-xs text-muted-foreground">{c.latencyMs}ms</p>}
              </div>
              <StatusDot status={c.status} />
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
