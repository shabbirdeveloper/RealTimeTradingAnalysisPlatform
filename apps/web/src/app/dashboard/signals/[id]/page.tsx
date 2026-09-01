import { notFound } from "next/navigation";
import Link from "next/link";
import { findSignalById } from "@/data/lookup";
import { ASSET_CONFIGS } from "@/data/assets";
import { ECONOMIC_EVENTS } from "@/data/history";
import { DirectionBadge, GradeBadge, RegimeBadge, DemoDataBanner } from "@/components/shared/badges";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { CountdownBadge } from "@/components/dashboard/countdown";
import { MiniPriceChart } from "@/components/dashboard/mini-price-chart";
import { expirySecondsOf, formatDateTimeUTC, formatExpiry, formatPercent, formatPrice } from "@/lib/utils";
import { ArrowLeft, CheckCircle2, XCircle, MinusCircle } from "lucide-react";

export default async function SignalDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const signal = findSignalById(id);
  if (!signal) notFound();

  const cfg = ASSET_CONFIGS[signal.asset];
  const isNoTrade = signal.direction === "NO_TRADE";
  const relatedNews = ECONOMIC_EVENTS.filter((e) => e.affectsAssets.includes(signal.asset)).slice(0, 3);

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <Link href="/dashboard/signals" className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeft className="h-4 w-4" /> Back to Live Signals
      </Link>

      <DemoDataBanner />

      <Card>
        <CardHeader className="flex-row items-start justify-between space-y-0">
          <div>
            <p className="text-xs text-muted-foreground">{cfg.displayName} · {signal.id}</p>
            <div className="mt-1 flex items-center gap-2">
              <DirectionBadge direction={signal.direction} className="text-sm" />
              {!isNoTrade && <GradeBadge grade={signal.grade} />}
              <RegimeBadge regime={signal.marketRegime} />
            </div>
          </div>
          {signal.validUntil && !signal.result && <CountdownBadge validUntil={signal.validUntil} />}
          {signal.result && <ResultPill result={signal.result} />}
        </CardHeader>
        <CardContent className="space-y-5">
          {!isNoTrade && signal.entryPrice && (
            <MiniPriceChart id={signal.id} entryPrice={signal.entryPrice} direction={signal.direction} />
          )}

          <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            <Field label="Generated" value={formatDateTimeUTC(signal.generatedAt)} />
            <Field label="Entry price" value={signal.entryPrice ? formatPrice(signal.entryPrice, cfg.pipDecimal) : "—"} />
            <Field label="Expiry" value={formatExpiry(expirySecondsOf(signal))} />
            <Field label="Closing price" value={signal.closingPrice ? formatPrice(signal.closingPrice, cfg.pipDecimal) : "—"} />
            <Field label="Technical score" value={`${signal.technicalScore}/100`} />
            <Field label="Model confidence" value={signal.confidence !== null ? formatPercent(signal.confidence) : "Not available"} />
            <Field label="Model version" value={signal.modelVersion ?? "MODEL_NOT_READY"} />
            <Field label="Session" value={signal.session.replace("_", " ")} />
          </div>

          {(signal.reasons.length > 0 || signal.warnings.length > 0) && (
            <div className="space-y-2 border-t border-border pt-4">
              {signal.reasons.map((r, i) => (
                <p key={`r-${i}`} className="flex gap-2 text-sm text-muted-foreground">
                  <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-call" /> {r}
                </p>
              ))}
              {signal.warnings.map((w, i) => (
                <p key={`w-${i}`} className="flex gap-2 text-sm text-notrade-foreground">
                  <MinusCircle className="mt-0.5 h-4 w-4 shrink-0 text-notrade" /> {w}
                </p>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {signal.timeframes.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Multi-Timeframe Analysis</CardTitle>
          </CardHeader>
          <CardContent className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {signal.timeframes.map((tf) => (
              <div key={tf.timeframe} className="rounded-md border border-border p-3">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-semibold text-foreground">{tf.timeframe}</span>
                  <span
                    className={
                      tf.bias === "BULLISH" ? "text-xs font-medium text-call" : tf.bias === "BEARISH" ? "text-xs font-medium text-put" : "text-xs font-medium text-muted-foreground"
                    }
                  >
                    {tf.bias}
                  </span>
                </div>
                <div className="mt-2 h-1.5 w-full rounded-full bg-secondary">
                  <div
                    className={`h-full rounded-full ${tf.bias === "BULLISH" ? "bg-call" : tf.bias === "BEARISH" ? "bg-put" : "bg-notrade"}`}
                    style={{ width: `${tf.strength}%` }}
                  />
                </div>
                <p className="mt-2 text-xs text-muted-foreground">{tf.notes[0]}</p>
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>News Context</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {relatedNews.length === 0 && <p className="text-sm text-muted-foreground">No relevant scheduled events nearby.</p>}
            {relatedNews.map((ev) => (
              <div key={ev.id} className="flex items-center justify-between text-sm">
                <span className="text-foreground">{ev.event} <span className="text-muted-foreground">({ev.currency})</span></span>
                <span className="text-xs text-muted-foreground">{formatDateTimeUTC(ev.dateTime)}</span>
              </div>
            ))}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Final Result</CardTitle>
          </CardHeader>
          <CardContent>
            {signal.result ? (
              <div className="flex items-center gap-3">
                <ResultPill result={signal.result} large />
                <p className="text-sm text-muted-foreground">
                  Resolved {signal.resolvedAt ? formatDateTimeUTC(signal.resolvedAt) : "—"} at {signal.closingPrice ? formatPrice(signal.closingPrice, cfg.pipDecimal) : "—"}.
                </p>
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">
                {isNoTrade ? "No trade was generated for this cycle — nothing to resolve." : "This signal has not reached expiry yet."}
              </p>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-[11px] uppercase tracking-wide text-muted-foreground">{label}</p>
      <p className="font-mono-tabular text-sm font-medium text-foreground">{value}</p>
    </div>
  );
}

function ResultPill({ result, large }: { result: "WON" | "LOST" | "DRAW"; large?: boolean }) {
  const size = large ? "h-8 w-8" : "h-3.5 w-3.5";
  if (result === "WON") return <span className={`flex items-center gap-1.5 font-semibold text-call ${large ? "text-lg" : "text-sm"}`}><CheckCircle2 className={size} /> WIN</span>;
  if (result === "LOST") return <span className={`flex items-center gap-1.5 font-semibold text-put ${large ? "text-lg" : "text-sm"}`}><XCircle className={size} /> LOSS</span>;
  return <span className={`flex items-center gap-1.5 font-semibold text-notrade ${large ? "text-lg" : "text-sm"}`}><MinusCircle className={size} /> DRAW</span>;
}
