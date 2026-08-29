"use client";
import { useState } from "react";
import { ASSET_LIST, ASSET_CONFIGS } from "@/data/assets";
import { buildDemoBacktest, ANCHOR_DATE } from "@/data/history";
import type { AssetSymbol, BacktestResult, ExpiryMinutes } from "@/types";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { DemoDataBanner } from "@/components/shared/badges";
import { formatPercent } from "@/lib/utils";

const thirtyDaysAgo = new Date(ANCHOR_DATE.getTime() - 30 * 86400000).toISOString().slice(0, 10);
const today = ANCHOR_DATE.toISOString().slice(0, 10);

export default function AdminBacktestingPage() {
  const [asset, setAsset] = useState<string>("ALL");
  const [expiry, setExpiry] = useState<string>("ALL");
  const [start, setStart] = useState(thirtyDaysAgo);
  const [end, setEnd] = useState(today);
  const [minConfidence, setMinConfidence] = useState(80);
  const [result, setResult] = useState<BacktestResult | null>(null);

  const run = () => {
    setResult(
      buildDemoBacktest({
        asset: asset === "ALL" ? "ALL" : (asset as AssetSymbol),
        expiryMinutes: expiry === "ALL" ? "ALL" : (Number(expiry) as ExpiryMinutes),
        startDate: start,
        endDate: end,
        minConfidence,
      })
    );
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold tracking-tight text-foreground">Backtesting</h1>
        <p className="text-sm text-muted-foreground">Runs against stored demo history — no look-ahead, no future data in feature calculation.</p>
      </div>
      <DemoDataBanner />

      <Card>
        <CardContent className="grid grid-cols-2 gap-4 p-5 sm:grid-cols-3 lg:grid-cols-6">
          <Field label="Asset">
            <Select value={asset} onValueChange={setAsset}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="ALL">All assets</SelectItem>
                {ASSET_LIST.map((a) => <SelectItem key={a} value={a}>{ASSET_CONFIGS[a].displayName}</SelectItem>)}
              </SelectContent>
            </Select>
          </Field>
          <Field label="Expiry">
            <Select value={expiry} onValueChange={setExpiry}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="ALL">All expiries</SelectItem>
                <SelectItem value="15">15 min</SelectItem>
                <SelectItem value="30">30 min</SelectItem>
                <SelectItem value="60">60 min</SelectItem>
              </SelectContent>
            </Select>
          </Field>
          <Field label="Start date">
            <Input type="date" value={start} onChange={(e) => setStart(e.target.value)} />
          </Field>
          <Field label="End date">
            <Input type="date" value={end} onChange={(e) => setEnd(e.target.value)} />
          </Field>
          <Field label="Min confidence">
            <Input type="number" min={0} max={100} value={minConfidence} onChange={(e) => setMinConfidence(Number(e.target.value))} />
          </Field>
          <div className="flex items-end">
            <Button onClick={run} className="w-full">Run backtest</Button>
          </div>
        </CardContent>
      </Card>

      {result && (
        <>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-6">
            <Stat label="Opportunities" value={String(result.totalOpportunities)} />
            <Stat label="Accepted" value={String(result.accepted)} />
            <Stat label="Rejected" value={String(result.rejected)} />
            <Stat label="Wins / losses" value={`${result.wins} / ${result.losses}`} />
            <Stat label="Win rate" value={formatPercent(result.winRate)} />
            <Stat label="Max streaks" value={`W${result.maxWinStreak} / L${result.maxLossStreak}`} />
          </div>
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <BreakdownTable title="By asset" rows={result.byAsset} />
            <BreakdownTable title="By expiry" rows={result.byExpiry} />
            <BreakdownTable title="By session" rows={result.bySession} />
            <BreakdownTable title="By regime" rows={result.byRegime} />
          </div>
        </>
      )}
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1.5">
      <Label>{label}</Label>
      {children}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <Card>
      <CardContent className="p-4">
        <p className="text-[11px] uppercase tracking-wide text-muted-foreground">{label}</p>
        <p className="font-mono-tabular text-lg font-semibold text-foreground">{value}</p>
      </CardContent>
    </Card>
  );
}

function BreakdownTable({ title, rows }: { title: string; rows: { label: string; signals: number; accuracy: number }[] }) {
  return (
    <Card>
      <CardHeader><CardTitle>{title}</CardTitle></CardHeader>
      <CardContent className="space-y-2">
        {rows.map((r) => (
          <div key={r.label} className="flex items-center justify-between text-sm">
            <span className="text-foreground">{r.label}</span>
            <span className="font-mono-tabular text-muted-foreground">{r.signals} sig · {formatPercent(r.accuracy)}</span>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}
