"use client";
import { useNow } from "@/lib/use-now";
import { ASSET_CONFIGS } from "@/data/assets";
import { generateMarketSnapshot, generateSignal, generateTechnicalMetrics, generateStructureNotes } from "@/data/engine";
import { HISTORICAL_SIGNALS, PERFORMANCE_SUMMARY } from "@/data/history";
import type { AssetSymbol } from "@/types";
import type { AssetPriceSnapshot } from "@/lib/market-data";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { DirectionBadge, GradeBadge, RegimeBadge, DataStatusPill, DemoDataBanner } from "@/components/shared/badges";
import { Skeleton } from "@/components/ui/skeleton";
import { formatDateTimeUTC, formatPercent, formatPrice } from "@/lib/utils";
import { ArrowUpRight, ArrowDownRight, Minus, AlertTriangle } from "lucide-react";

/**
 * Real price/24h-change/data-status when the market-data collector has
 * written candles for this asset (priceSnapshot from Supabase, passed
 * down from the async page component). Everything else on this page --
 * bias, regime, indicators, structure, signal, expiry candidates, signal
 * history, performance -- stays the frontend demo engine, honestly
 * labeled, until the real feature/regime/signal engine (Phases 3-4) and
 * backtesting (Phase 5) exist. Never mix a real price with a fabricated
 * confidence/result -- spec section 50.
 */
export function MarketPageContent({ asset, priceSnapshot }: { asset: AssetSymbol; priceSnapshot?: AssetPriceSnapshot | null }) {
  const now = useNow(1000);
  const cfg = ASSET_CONFIGS[asset];

  if (!now) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-40 w-full" />
        <Skeleton className="h-72 w-full" />
      </div>
    );
  }

  const demoSnapshot = generateMarketSnapshot(asset, now);
  const signal = generateSignal(asset, now);
  const technical = generateTechnicalMetrics(asset, now);
  const structure = generateStructureNotes(asset, now);
  const recentSignals = HISTORICAL_SIGNALS.filter((s) => s.asset === asset).slice(0, 8);
  const perf = PERFORMANCE_SUMMARY.byAsset.find((b) => b.label === asset);

  const hasRealPrice = Boolean(priceSnapshot);
  const price = priceSnapshot?.price ?? demoSnapshot.price;
  const change24hPct = priceSnapshot?.change24hPct ?? demoSnapshot.change24hPct;
  const dataStatus = priceSnapshot?.dataStatus ?? demoSnapshot.dataStatus;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold tracking-tight text-foreground">{cfg.displayName}</h1>
          <p className="text-sm text-muted-foreground">{cfg.contextFactors.join(" · ")}</p>
        </div>
        <div className="flex items-center gap-2">
          <DataStatusPill status={dataStatus} />
          <RegimeBadge regime={demoSnapshot.regime} />
        </div>
      </div>

      {hasRealPrice ? (
        <div className="flex items-start gap-2.5 rounded-lg border border-notrade/20 bg-notrade-muted/40 px-3.5 py-2 text-xs text-notrade-foreground/90">
          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-notrade" />
          <span>
            <strong className="font-semibold">Price and 24h change above are live</strong> from the market-data
            collector. Everything else on this page — bias, regime, indicators, structure, signals, and performance —
            is still a <strong className="font-semibold">synthetic placeholder</strong>; the regime/signal/ML engine
            (Phases 3–4) and backtesting (Phase 5) haven&apos;t been built yet.
          </span>
        </div>
      ) : (
        <DemoDataBanner />
      )}

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Stat label="Price" value={formatPrice(price, cfg.pipDecimal)} />
        <Stat
          label="24h change"
          value={
            <span className={`flex items-center gap-0.5 ${change24hPct > 0 ? "text-call" : change24hPct < 0 ? "text-put" : "text-muted-foreground"}`}>
              {change24hPct > 0 ? <ArrowUpRight className="h-3.5 w-3.5" /> : change24hPct < 0 ? <ArrowDownRight className="h-3.5 w-3.5" /> : <Minus className="h-3.5 w-3.5" />}
              {formatPercent(Math.abs(change24hPct))}
            </span>
          }
        />
        <Stat label="Session" value={demoSnapshot.session.replace("_", " ")} />
        <Stat label="Bias (H4)" value={demoSnapshot.bias} />
      </div>

      <Tabs defaultValue="overview">
        <TabsList className="flex-wrap">
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="technical">Technical</TabsTrigger>
          <TabsTrigger value="structure">Structure</TabsTrigger>
          <TabsTrigger value="ai">AI Analysis</TabsTrigger>
          <TabsTrigger value="signals">Signals</TabsTrigger>
          <TabsTrigger value="performance">Performance</TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="space-y-4">
          <Card>
            <CardHeader><CardTitle>Multi-Timeframe Bias</CardTitle></CardHeader>
            <CardContent className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              {demoSnapshot.timeframes.map((tf) => (
                <div key={tf.timeframe} className="rounded-md border border-border p-3">
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-semibold">{tf.timeframe}</span>
                    <span className={tf.bias === "BULLISH" ? "text-xs text-call" : tf.bias === "BEARISH" ? "text-xs text-put" : "text-xs text-muted-foreground"}>{tf.bias}</span>
                  </div>
                  <p className="mt-1.5 text-xs text-muted-foreground">{tf.notes[0]}</p>
                </div>
              ))}
            </CardContent>
          </Card>
          <Card>
            <CardHeader><CardTitle>Current Signal</CardTitle></CardHeader>
            <CardContent className="flex flex-wrap items-center gap-3">
              <DirectionBadge direction={signal.direction} />
              {signal.direction !== "NO_TRADE" && <GradeBadge grade={signal.grade} />}
              <span className="text-sm text-muted-foreground">
                {signal.direction === "NO_TRADE" ? signal.warnings[0] ?? signal.reasons[0] : `${signal.confidence !== null ? formatPercent(signal.confidence) : "N/A confidence"} · ${signal.expiryMinutes}m expiry`}
              </span>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="technical">
          <Card>
            <CardHeader><CardTitle>Indicators</CardTitle></CardHeader>
            <CardContent className="grid grid-cols-2 gap-4 sm:grid-cols-3">
              <Stat label="RSI (14)" value={`${technical.rsi} · ${technical.rsiSlope}`} />
              <Stat label="MACD histogram" value={`${technical.macdHistogram} (${technical.macdTrend.toLowerCase()})`} />
              <Stat label="EMA structure" value={technical.priceVsEma.replace("_", " ")} />
              <Stat label="EMA 20" value={formatPrice(technical.ema20, cfg.pipDecimal)} />
              <Stat label="EMA 50" value={formatPrice(technical.ema50, cfg.pipDecimal)} />
              <Stat label="EMA 200" value={formatPrice(technical.ema200, cfg.pipDecimal)} />
              <Stat label="ATR" value={formatPrice(technical.atr, cfg.pipDecimal)} />
              <Stat label="ATR percentile" value={`${technical.atrPercentile}%`} />
              <Stat label="Bollinger width" value={`${technical.bollingerWidth}%`} />
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="structure">
          <Card>
            <CardHeader><CardTitle>Market Structure</CardTitle></CardHeader>
            <CardContent>
              <ul className="space-y-2 text-sm text-muted-foreground">
                {structure.map((s, i) => <li key={i}>• {s}</li>)}
              </ul>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="ai">
          <Card>
            <CardHeader><CardTitle>Expiry Analysis</CardTitle></CardHeader>
            <CardContent>
              {signal.candidates ? (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Expiry</TableHead>
                      <TableHead>Direction</TableHead>
                      <TableHead>Technical score</TableHead>
                      <TableHead>Model confidence</TableHead>
                      <TableHead>Meta model</TableHead>
                      <TableHead>Grade</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {signal.candidates.map((c) => (
                      <TableRow key={c.expiryMinutes} className={c.expiryMinutes === signal.expiryMinutes ? "bg-primary/5" : undefined}>
                        <TableCell>{c.expiryMinutes} min</TableCell>
                        <TableCell><DirectionBadge direction={c.direction} /></TableCell>
                        <TableCell className="font-mono-tabular">{c.technicalScore}/100</TableCell>
                        <TableCell className="font-mono-tabular">{c.modelConfidence !== null ? formatPercent(c.modelConfidence) : "MODEL_NOT_READY"}</TableCell>
                        <TableCell>{c.metaDecision ?? "—"}</TableCell>
                        <TableCell><GradeBadge grade={c.grade} /></TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              ) : (
                <p className="text-sm text-muted-foreground">No directional candidates this cycle — {signal.warnings[0] ?? "conflicting timeframes."}</p>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="signals">
          <Card>
            <CardHeader><CardTitle>Recent Signals</CardTitle></CardHeader>
            <CardContent>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Time</TableHead>
                    <TableHead>Direction</TableHead>
                    <TableHead>Grade</TableHead>
                    <TableHead>Expiry</TableHead>
                    <TableHead>Result</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {recentSignals.map((s) => (
                    <TableRow key={s.id}>
                      <TableCell className="text-xs text-muted-foreground">{formatDateTimeUTC(s.generatedAt)}</TableCell>
                      <TableCell><DirectionBadge direction={s.direction} /></TableCell>
                      <TableCell><GradeBadge grade={s.grade} /></TableCell>
                      <TableCell>{s.expiryMinutes}m</TableCell>
                      <TableCell className={s.result === "WON" ? "text-call" : s.result === "LOST" ? "text-put" : "text-muted-foreground"}>{s.result}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="performance">
          <Card>
            <CardHeader><CardTitle>Performance</CardTitle></CardHeader>
            <CardContent className="grid grid-cols-2 gap-4 sm:grid-cols-4">
              <Stat label="Signals" value={String(perf?.signals ?? 0)} />
              <Stat label="Wins" value={String(perf?.wins ?? 0)} />
              <Stat label="Losses" value={String(perf?.losses ?? 0)} />
              <Stat label="Accuracy" value={formatPercent(perf?.accuracy ?? 0)} />
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div>
      <p className="text-[11px] uppercase tracking-wide text-muted-foreground">{label}</p>
      <p className="font-mono-tabular text-sm font-semibold text-foreground">{value}</p>
    </div>
  );
}
