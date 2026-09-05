"use client";
import { useNow } from "@/lib/use-now";
import { ASSET_CONFIGS } from "@/data/assets";
import { generateMarketSnapshot, generateSignal, generateTechnicalMetrics, generateStructureNotes } from "@/data/engine";
import { HISTORICAL_SIGNALS, PERFORMANCE_SUMMARY } from "@/data/history";
import type { AssetSymbol, MarketAssetSymbol, Signal } from "@/types";
import type { AssetPriceSnapshot } from "@/lib/market-data";
import type { RealStructureReading, RealTechnicalMetrics } from "@/lib/features";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { DirectionBadge, GradeBadge, RegimeBadge, DataStatusPill, DemoDataBanner } from "@/components/shared/badges";
import { Skeleton } from "@/components/ui/skeleton";
import { expirySecondsOf, formatDateTimeUTC, formatExpiry, formatPercent, formatPrice } from "@/lib/utils";
import { ArrowUpRight, ArrowDownRight, Minus, AlertTriangle } from "lucide-react";
import { MarketClosedNotice } from "@/components/dashboard/market-closed-notice";
import { isMarketOpen } from "@/lib/market-hours";

/**
 * Real price/signal/features when apps/api's collector + signal engine
 * have produced them for this asset (passed down from the async page
 * component, which reads Supabase directly). Falls back to the frontend
 * demo engine, clearly labeled, wherever real data doesn't exist yet:
 * signal history and performance stats still need real resolved
 * outcomes to accumulate (spec section 49's resolution job and Phase 5
 * backtesting aren't built), so those two tabs stay demo. Never mix a
 * real number with a fabricated one inside the same stat -- spec section
 * 50.
 */
export function MarketPageContent({
  asset,
  priceSnapshot,
  signal: realSignal,
  features,
}: {
  asset: MarketAssetSymbol;
  priceSnapshot?: AssetPriceSnapshot | null;
  signal?: Signal | null;
  features?: { technical: RealTechnicalMetrics; structure: RealStructureReading } | null;
}) {
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
  const demoSignal = generateSignal(asset, now);
  const demoTechnical = generateTechnicalMetrics(asset, now);
  const demoStructureNotes = generateStructureNotes(asset, now);
  const recentSignals = HISTORICAL_SIGNALS.filter((s) => s.asset === asset).slice(0, 8);
  const perf = PERFORMANCE_SUMMARY.byAsset.find((b) => b.label === asset);

  const hasRealPrice = Boolean(priceSnapshot);
  const hasRealSignal = Boolean(realSignal);
  const hasRealFeatures = Boolean(features);

  const price = priceSnapshot?.price ?? demoSnapshot.price;
  const change24hPct = priceSnapshot?.change24hPct ?? demoSnapshot.change24hPct;
  const dataStatus = priceSnapshot?.dataStatus ?? demoSnapshot.dataStatus;
  const regime = realSignal?.marketRegime ?? demoSnapshot.regime;
  const timeframes = hasRealSignal && realSignal!.timeframes.length ? realSignal!.timeframes : demoSnapshot.timeframes;
  const signal = realSignal ?? demoSignal;
  const candidates = hasRealSignal ? realSignal!.candidates : demoSignal.candidates;
  const technical = features?.technical;
  const structure = features?.structure;
  const closed = !isMarketOpen(asset, now);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold tracking-tight text-foreground">{cfg.displayName}</h1>
          <p className="text-sm text-muted-foreground">{cfg.contextFactors.join(" · ")}</p>
        </div>
        <div className="flex items-center gap-2">
          {!closed && <DataStatusPill status={dataStatus} />}
          <RegimeBadge regime={regime} />
        </div>
      </div>

      {closed && <MarketClosedNotice asset={asset} />}

      {hasRealPrice ? (
        <div className="flex items-start gap-2.5 rounded-lg border border-notrade/20 bg-notrade-muted/40 px-3.5 py-2 text-xs text-notrade-foreground/90">
          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-notrade" />
          <span>
            {hasRealSignal ? (
              <>
                <strong className="font-semibold">Price, regime, and the signal below are real</strong> — computed
                by the technical signal engine from live candles.{" "}
                {hasRealFeatures
                  ? "Technical/Structure tabs are real too."
                  : "Technical/Structure tabs are still demo (no feature snapshot for this timeframe yet)."}{" "}
                No calibrated ML confidence yet (Phase 6), so grade is capped at B. Signal history and performance
                stay demo until resolved outcomes accumulate.
              </>
            ) : (
              <>
                <strong className="font-semibold">Price and 24h change above are live.</strong> Signal analysis for
                this asset hasn&apos;t completed its first cycle yet — everything below is still a{" "}
                <strong className="font-semibold">synthetic placeholder</strong>.
              </>
            )}
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
              {timeframes.map((tf) => (
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
                {signal.direction === "NO_TRADE" ? signal.warnings[0] ?? signal.reasons[0] : `${signal.confidence !== null ? formatPercent(signal.confidence) : "N/A confidence"} · ${formatExpiry(expirySecondsOf(signal))} expiry`}
              </span>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="technical">
          <Card>
            <CardHeader><CardTitle>Indicators</CardTitle></CardHeader>
            <CardContent className="grid grid-cols-2 gap-4 sm:grid-cols-3">
              {technical ? (
                <>
                  <Stat label="RSI (14)" value={technical.rsi !== null ? `${Math.round(technical.rsi)} · ${technical.rsiSlope ?? "—"}` : "—"} />
                  <Stat label="MACD histogram" value={technical.macdHistogram !== null ? `${technical.macdHistogram.toFixed(3)} (${(technical.macdTrend ?? "—").toLowerCase()})` : "—"} />
                  <Stat label="EMA structure" value={technical.priceVsEma ? technical.priceVsEma.replace("_", " ") : "—"} />
                  <Stat label="EMA 20" value={technical.ema20 !== null ? formatPrice(technical.ema20, cfg.pipDecimal) : "—"} />
                  <Stat label="EMA 50" value={technical.ema50 !== null ? formatPrice(technical.ema50, cfg.pipDecimal) : "—"} />
                  <Stat label="EMA 200" value={technical.ema200 !== null ? formatPrice(technical.ema200, cfg.pipDecimal) : "—"} />
                  <Stat label="ATR" value={technical.atr !== null ? formatPrice(technical.atr, cfg.pipDecimal) : "—"} />
                  <Stat label="ATR percentile" value={technical.atrPercentile !== null ? `${Math.round(technical.atrPercentile)}%` : "—"} />
                  <Stat label="Bollinger width" value={technical.bollingerWidth !== null ? `${technical.bollingerWidth.toFixed(1)}%` : "—"} />
                </>
              ) : (
                <>
                  <Stat label="RSI (14)" value={`${demoTechnical.rsi} · ${demoTechnical.rsiSlope}`} />
                  <Stat label="MACD histogram" value={`${demoTechnical.macdHistogram} (${demoTechnical.macdTrend.toLowerCase()})`} />
                  <Stat label="EMA structure" value={demoTechnical.priceVsEma.replace("_", " ")} />
                  <Stat label="EMA 20" value={formatPrice(demoTechnical.ema20, cfg.pipDecimal)} />
                  <Stat label="EMA 50" value={formatPrice(demoTechnical.ema50, cfg.pipDecimal)} />
                  <Stat label="EMA 200" value={formatPrice(demoTechnical.ema200, cfg.pipDecimal)} />
                  <Stat label="ATR" value={formatPrice(demoTechnical.atr, cfg.pipDecimal)} />
                  <Stat label="ATR percentile" value={`${demoTechnical.atrPercentile}%`} />
                  <Stat label="Bollinger width" value={`${demoTechnical.bollingerWidth}%`} />
                </>
              )}
            </CardContent>
          </Card>
          {!technical && (
            <p className="mt-3 text-xs text-muted-foreground">Demo values — no real H1 feature snapshot for this asset yet.</p>
          )}
        </TabsContent>

        <TabsContent value="structure">
          <Card>
            <CardHeader><CardTitle>Market Structure</CardTitle></CardHeader>
            <CardContent>
              {structure ? (
                <ul className="space-y-2 text-sm text-muted-foreground">
                  <li>• Swing sequence: {structure.sequence ? structure.sequence.replace("_", " / ") : "not enough swing points yet"}.</li>
                  {structure.support !== null && <li>• Support (last swing low): {formatPrice(structure.support, cfg.pipDecimal)}</li>}
                  {structure.resistance !== null && <li>• Resistance (last swing high): {formatPrice(structure.resistance, cfg.pipDecimal)}</li>}
                  {structure.bos && <li>• Break of structure — price has closed beyond the last swing level.</li>}
                  {structure.choch && <li>• Change of character — the prior trend structure just flipped.</li>}
                </ul>
              ) : (
                <ul className="space-y-2 text-sm text-muted-foreground">
                  {demoStructureNotes.map((s, i) => <li key={i}>• {s}</li>)}
                </ul>
              )}
            </CardContent>
          </Card>
          {!structure && (
            <p className="mt-3 text-xs text-muted-foreground">Demo values — no real H1 feature snapshot for this asset yet.</p>
          )}
        </TabsContent>

        <TabsContent value="ai">
          <Card>
            <CardHeader><CardTitle>Expiry Analysis</CardTitle></CardHeader>
            <CardContent>
              {candidates ? (
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
                    {candidates.map((c) => (
                      <TableRow key={c.expiryMinutes ?? c.expirySeconds} className={expirySecondsOf(c) === expirySecondsOf(signal) ? "bg-primary/5" : undefined}>
                        <TableCell>{formatExpiry(expirySecondsOf(c))}</TableCell>
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
              <p className="mb-3 text-xs text-muted-foreground">Demo history — real signal history accumulates over time as the engine runs; a searchable real history view is a follow-up step.</p>
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
              <p className="col-span-full mb-1 text-xs text-muted-foreground">Demo figures — real accuracy needs resolved signal outcomes, which the resolution job (spec section 49) doesn&apos;t exist yet to produce.</p>
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
