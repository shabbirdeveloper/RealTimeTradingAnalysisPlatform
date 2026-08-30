"use client";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { AccuracyVerdict } from "@/components/dashboard/accuracy-verdict";
import { formatPercent } from "@/lib/utils";
import type { PerformanceSummary } from "@/types";
import { Award, Target, TrendingUp, TrendingDown, Flame, Snowflake } from "lucide-react";
import {
  LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend,
} from "recharts";

const chartTooltip = { contentStyle: { background: "hsl(var(--popover))", border: "1px solid hsl(var(--border))", borderRadius: 8, fontSize: 12 } };
const axisStyle = { fontSize: 11, fill: "hsl(var(--muted-foreground))" };

/**
 * Renders real performance stats (see apps/web/src/lib/performance.ts).
 * A brand-new signal engine with no resolved history yet will
 * legitimately show all zeros here -- that's the honest starting state,
 * not a bug, and it's still real (never swapped for demo numbers to
 * look more finished).
 */
export function PerformanceCharts({ summary: p }: { summary: PerformanceSummary }) {
  return (
    <>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        <Kpi icon={Target} label="Total signals" value={String(p.totalSignals)} />
        <Kpi icon={TrendingUp} label="Wins" value={String(p.wins)} tone="call" />
        <Kpi icon={TrendingDown} label="Losses" value={String(p.losses)} tone="put" />
        <Kpi icon={Target} label="Overall accuracy" value={formatPercent(p.overallAccuracy)} />
        <Kpi icon={Award} label="A++ accuracy" value={formatPercent(p.aPlusPlusAccuracy)} tone="gold" sub={`${p.aPlusPlusSignals} signals`} />
        <Kpi icon={p.currentStreak.type === "LOSS" ? Snowflake : Flame} label="Current streak" value={`${p.currentStreak.count} ${p.currentStreak.type}`} />
      </div>

      <AccuracyVerdict wins={p.wins} losses={p.losses} />

      {p.totalSignals === 0 && (
        <p className="rounded-lg border border-dashed border-border bg-secondary/20 p-3.5 text-sm text-muted-foreground">
          No signals have resolved yet — figures above are real, just real-zero. They&apos;ll fill in as generated
          signals actually reach their expiry and get checked against the real closing price.
        </p>
      )}

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <Card>
          <CardHeader><CardTitle>Accuracy over time</CardTitle></CardHeader>
          <CardContent className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={p.accuracyOverTime}>
                <CartesianGrid stroke="hsl(var(--border))" strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="date" tick={axisStyle} tickLine={false} axisLine={false} minTickGap={24} />
                <YAxis domain={[0, 100]} tick={axisStyle} tickLine={false} axisLine={false} width={32} />
                <Tooltip {...chartTooltip} />
                <Line type="monotone" dataKey="accuracy" stroke="hsl(var(--primary))" strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle>Cumulative wins vs losses</CardTitle></CardHeader>
          <CardContent className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={p.cumulative}>
                <CartesianGrid stroke="hsl(var(--border))" strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="date" tick={axisStyle} tickLine={false} axisLine={false} minTickGap={24} />
                <YAxis tick={axisStyle} tickLine={false} axisLine={false} width={32} />
                <Tooltip {...chartTooltip} />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                <Line type="monotone" dataKey="wins" name="Wins" stroke="hsl(var(--call))" strokeWidth={2} dot={false} />
                <Line type="monotone" dataKey="losses" name="Losses" stroke="hsl(var(--put))" strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>

        <BreakdownCard title="Performance by asset" data={p.byAsset} />
        <BreakdownCard title="Performance by expiry" data={p.byExpiry} />
        <BreakdownCard title="Performance by session" data={p.bySession} />
        <BreakdownCard title="Performance by market regime" data={p.byRegime} />
        <BreakdownCard title="Performance by technical-score bucket" data={p.byConfidenceBucket} full />
      </div>
    </>
  );
}

function BreakdownCard({ title, data, full }: { title: string; data: PerformanceSummary["byAsset"]; full?: boolean }) {
  return (
    <Card className={full ? "xl:col-span-2" : undefined}>
      <CardHeader><CardTitle>{title}</CardTitle></CardHeader>
      <CardContent className="h-64">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data}>
            <CartesianGrid stroke="hsl(var(--border))" strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey="label" tick={axisStyle} tickLine={false} axisLine={false} />
            <YAxis domain={[0, 100]} tick={axisStyle} tickLine={false} axisLine={false} width={32} />
            <Tooltip {...chartTooltip} />
            <Bar dataKey="accuracy" name="Accuracy %" fill="hsl(var(--primary))" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  );
}

function Kpi({ icon: Icon, label, value, sub, tone }: { icon: typeof Target; label: string; value: string; sub?: string; tone?: "call" | "put" | "gold" }) {
  const iconCls =
    tone === "call" ? "bg-gradient-to-br from-call/25 to-call/5 text-call ring-call/25"
    : tone === "put" ? "bg-gradient-to-br from-put/25 to-put/5 text-put ring-put/25"
    : tone === "gold" ? "bg-gradient-to-br from-aplusplus/25 to-aplusplus/5 text-aplusplus ring-aplusplus/25"
    : "bg-gradient-to-br from-primary/20 to-primary/5 text-primary ring-primary/20";
  return (
    <Card className="card-premium-hover">
      <CardContent className="p-4">
        <span className={`mb-2.5 flex h-9 w-9 items-center justify-center rounded-lg ring-1 ring-inset ${iconCls}`}>
          <Icon className="h-4 w-4" />
        </span>
        <p className="text-[10.5px] font-medium uppercase tracking-wider text-muted-foreground">{label}</p>
        <p className="font-mono-tabular text-lg font-semibold text-foreground">{value}</p>
        {sub && <p className="text-[11px] text-muted-foreground">{sub}</p>}
      </CardContent>
    </Card>
  );
}
