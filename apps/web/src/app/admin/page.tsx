import { Card, CardContent } from "@/components/ui/card";
import { DemoDataBanner } from "@/components/shared/badges";
import { PERFORMANCE_SUMMARY, HISTORICAL_SIGNALS, SYSTEM_HEALTH, ANCHOR_DATE } from "@/data/history";
import { formatPercent } from "@/lib/utils";
import { Users, UserCheck, CreditCard, Radio, Award, Target } from "lucide-react";
import { StatusDot } from "@/components/admin/status-dot";

const todaySignals = HISTORICAL_SIGNALS.filter((s) => s.generatedAt.slice(0, 10) === ANCHOR_DATE.toISOString().slice(0, 10));
const todayAplusplus = todaySignals.filter((s) => s.grade === "A++");

export default function AdminOverviewPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold tracking-tight text-foreground">Overview</h1>
        <p className="text-sm text-muted-foreground">Platform-wide status as of {ANCHOR_DATE.toISOString().slice(0, 10)}.</p>
      </div>

      <DemoDataBanner />

      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        <Tile icon={Users} label="Total users" value="1,284" />
        <Tile icon={UserCheck} label="Active users (7d)" value="612" />
        <Tile icon={CreditCard} label="Subscribers" value="197" />
        <Tile icon={Radio} label="Signals today" value={String(todaySignals.length)} />
        <Tile icon={Award} label="A++ signals today" value={String(todayAplusplus.length)} tone="gold" />
        <Tile icon={Target} label="Signal accuracy" value={formatPercent(PERFORMANCE_SUMMARY.overallAccuracy)} />
      </div>

      <Card>
        <CardContent className="grid grid-cols-2 gap-4 p-5 sm:grid-cols-3 lg:grid-cols-5">
          {SYSTEM_HEALTH.map((c) => (
            <div key={c.name} className="flex items-center justify-between rounded-md border border-border p-3">
              <span className="text-sm text-foreground">{c.name}</span>
              <StatusDot status={c.status} />
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}

function Tile({ icon: Icon, label, value, tone }: { icon: typeof Users; label: string; value: string; tone?: "gold" }) {
  return (
    <Card className="card-premium-hover">
      <CardContent className="p-4">
        <span className={`mb-2.5 flex h-9 w-9 items-center justify-center rounded-lg ring-1 ring-inset ${tone === "gold" ? "bg-gradient-to-br from-aplusplus/25 to-aplusplus/5 text-aplusplus ring-aplusplus/25" : "bg-gradient-to-br from-primary/20 to-primary/5 text-primary ring-primary/20"}`}>
          <Icon className="h-4 w-4" />
        </span>
        <p className="text-[10.5px] font-medium uppercase tracking-wider text-muted-foreground">{label}</p>
        <p className="font-mono-tabular text-lg font-semibold text-foreground">{value}</p>
      </CardContent>
    </Card>
  );
}
