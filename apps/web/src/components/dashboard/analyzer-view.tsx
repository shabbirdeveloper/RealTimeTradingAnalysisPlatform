"use client";
import { useState } from "react";
import { ASSET_LIST, ASSET_CONFIGS } from "@/data/assets";
import type { AssetSymbol, ExpiryMinutes, Signal } from "@/types";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { DirectionBadge, GradeBadge, RegimeBadge } from "@/components/shared/badges";
import { formatPercent } from "@/lib/utils";
import { Label } from "@/components/ui/label";

const EXPIRIES: ExpiryMinutes[] = [15, 30, 60];

export function AnalyzerView({ signals }: { signals: Record<AssetSymbol, Signal | null> }) {
  const [asset, setAsset] = useState<AssetSymbol>("XAUUSD");
  const [expiry, setExpiry] = useState<ExpiryMinutes>(30);

  const signal = signals[asset];
  const candidate = signal?.candidates?.find((c) => c.expiryMinutes === expiry);
  const cfg = ASSET_CONFIGS[asset];

  return (
    <div className="space-y-6">
      <Card>
        <CardContent className="flex flex-wrap gap-4 p-5">
          <div className="min-w-[160px] flex-1 space-y-1.5">
            <Label>Asset</Label>
            <Select value={asset} onValueChange={(v) => setAsset(v as AssetSymbol)}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                {ASSET_LIST.map((a) => (
                  <SelectItem key={a} value={a}>{ASSET_CONFIGS[a].displayName}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="min-w-[160px] flex-1 space-y-1.5">
            <Label>Expiry</Label>
            <Select value={String(expiry)} onValueChange={(v) => setExpiry(Number(v) as ExpiryMinutes)}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                {EXPIRIES.map((e) => (
                  <SelectItem key={e} value={String(e)}>{e} minutes</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </CardContent>
      </Card>

      {!signal ? (
        <Card>
          <CardContent className="p-5 text-sm text-muted-foreground">
            No signal analysis yet for {cfg.displayName} — the engine hasn&apos;t completed a cycle for this asset, or
            there isn&apos;t enough real candle history yet. Check back after the next 5-minute analysis cycle.
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardHeader>
            <CardTitle>{cfg.displayName} · {expiry}m Analysis</CardTitle>
          </CardHeader>
          <CardContent className="space-y-5">
            <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
              <Row label="Trend (H4)" value={signal.timeframes.find((t) => t.timeframe === "H4")?.bias ?? "—"} />
              <Row label="Market regime" value={<RegimeBadge regime={signal.marketRegime} />} />
              <Row label="Technical score" value={`${candidate?.technicalScore ?? signal.technicalScore}/100`} />
              <Row label="ML probability" value={candidate?.modelConfidence !== null && candidate?.modelConfidence !== undefined ? formatPercent(candidate.modelConfidence) : "MODEL_NOT_READY"} />
              <Row label="Meta model" value={candidate?.metaDecision ?? "Not available (Phase 6)"} />
              <Row label="Grade" value={candidate ? <GradeBadge grade={candidate.grade} /> : <GradeBadge grade="REJECTED" />} />
            </div>

            <div className="rounded-md border border-border bg-secondary/30 p-4">
              <p className="text-[11px] uppercase tracking-wide text-muted-foreground">Final</p>
              {signal.direction === "NO_TRADE" || !candidate || candidate.direction !== signal.direction || expiry !== signal.expiryMinutes ? (
                <div className="mt-1 space-y-1">
                  <DirectionBadge direction="NO_TRADE" className="text-sm" />
                  <p className="text-sm text-muted-foreground">
                    Reason: {signal.direction === "NO_TRADE" ? (signal.warnings[0] ?? signal.reasons[0]) : `${expiry}m is not the strongest expiry this cycle — see best expiry (${signal.expiryMinutes}m) on the live signal.`}
                  </p>
                </div>
              ) : (
                <div className="mt-1 flex items-center gap-2">
                  <DirectionBadge direction={signal.direction} className="text-sm" />
                  <GradeBadge grade={signal.grade} />
                </div>
              )}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div>
      <p className="text-[11px] uppercase tracking-wide text-muted-foreground">{label}</p>
      <p className="text-sm font-medium text-foreground">{value}</p>
    </div>
  );
}
