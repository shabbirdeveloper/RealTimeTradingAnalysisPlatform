"use client";
import Link from "next/link";
import { Card, CardContent } from "@/components/ui/card";
import { DirectionBadge, GradeBadge, RegimeBadge } from "@/components/shared/badges";
import { ASSET_CONFIGS } from "@/data/assets";
import type { Signal } from "@/types";
import { cn, formatCountdown, formatDateTimeUTC, formatPercent, formatPrice } from "@/lib/utils";
import { Clock, Sparkles } from "lucide-react";

export function LiveSignalCard({ signal, now }: { signal: Signal; now: Date }) {
  const cfg = ASSET_CONFIGS[signal.asset];
  const isNoTrade = signal.direction === "NO_TRADE";
  const msRemaining = signal.validUntil ? new Date(signal.validUntil).getTime() - now.getTime() : 0;
  const isAplusplus = signal.grade === "A++";
  const accent = signal.direction === "CALL" ? "bg-call" : signal.direction === "PUT" ? "bg-put" : "bg-notrade/70";

  return (
    <Card
      className={cn(
        "card-premium-hover overflow-hidden",
        isAplusplus && "aplusplus-frame border-aplusplus/30"
      )}
    >
      <div className={cn("h-[3px] w-full", accent)} />
      {isAplusplus && (
        <div className="flex items-center gap-1.5 bg-gradient-to-r from-aplusplus/20 via-aplusplus/10 to-transparent px-4 py-1.5 text-[11px] font-bold uppercase tracking-wider text-aplusplus">
          <Sparkles className="h-3 w-3" /> A++ Signal
        </div>
      )}
      <CardContent className="space-y-4 p-5">
        <div className="flex items-start justify-between">
          <div>
            <p className="text-base font-semibold text-foreground">{cfg.displayName}</p>
            <p className="text-xs text-muted-foreground">Generated {formatDateTimeUTC(signal.generatedAt)}</p>
          </div>
          <div className="flex items-center gap-2">
            <RegimeBadge regime={signal.marketRegime} />
            {!isNoTrade && <GradeBadge grade={signal.grade} />}
          </div>
        </div>

        <DirectionBadge direction={signal.direction} className="text-sm" />

        {isNoTrade ? (
          <p className="rounded-md border border-dashed border-border bg-secondary/30 p-3 text-sm text-muted-foreground">
            {signal.warnings[0] ?? signal.reasons[0] ?? "Market conditions not strong enough for a signal."}
          </p>
        ) : (
          <>
            <div className="grid grid-cols-2 gap-4 rounded-lg border border-border/70 bg-secondary/20 p-3.5 sm:grid-cols-4">
              <Metric label="Confidence" value={signal.confidence !== null ? formatPercent(signal.confidence) : "N/A"} />
              <Metric label="Expiry" value={`${signal.expiryMinutes} min`} />
              <Metric label="Entry" value={signal.entryPrice ? formatPrice(signal.entryPrice, cfg.pipDecimal) : "—"} />
              <Metric
                label="Valid for"
                value={
                  <span className="flex items-center gap-1 font-mono-tabular text-primary">
                    <Clock className="h-3.5 w-3.5" />
                    {formatCountdown(msRemaining)}
                  </span>
                }
              />
            </div>
            {signal.reasons.length > 0 && (
              <ul className="space-y-1 border-t border-border/70 pt-3 text-xs text-muted-foreground">
                {signal.reasons.map((r, i) => (
                  <li key={i}>• {r}</li>
                ))}
              </ul>
            )}
          </>
        )}

        <Link href={`/dashboard/signals/${signal.id}`} className="inline-flex items-center gap-1 text-xs font-semibold text-primary hover:underline">
          View full analysis →
        </Link>
      </CardContent>
    </Card>
  );
}

function Metric({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div>
      <p className="text-[10.5px] font-medium uppercase tracking-wider text-muted-foreground">{label}</p>
      <p className="font-mono-tabular text-sm font-semibold text-foreground">{value}</p>
    </div>
  );
}
