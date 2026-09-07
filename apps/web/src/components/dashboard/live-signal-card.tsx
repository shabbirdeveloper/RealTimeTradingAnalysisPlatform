"use client";
import Link from "next/link";
import { Card, CardContent } from "@/components/ui/card";
import { DirectionBadge, GradeBadge, RegimeBadge } from "@/components/shared/badges";
import { AnimatedNumber } from "@/components/shared/animated-number";
import { ASSET_CONFIGS } from "@/data/assets";
import type { Signal } from "@/types";
import { cn, expirySecondsOf, formatCountdown, formatDateTimeUTC, formatExpiry, formatPrice, formatRelative, isCheckStale } from "@/lib/utils";
import { Clock, Sparkles } from "lucide-react";
import { DecisionChecks } from "@/components/dashboard/decision-checks";

export function LiveSignalCard({
  signal,
  now,
  index = 0,
  staleNote = "engine may be stopped",
}: {
  signal: Signal;
  now: Date;
  index?: number;
  /** What a stale card means HERE. "Engine may be stopped" is a guess, and
   *  the wrong one when a collector is deliberately switched off; the
   *  server knows which and passes it down. */
  staleNote?: string;
}) {
  const cfg = ASSET_CONFIGS[signal.asset];
  const isNoTrade = signal.direction === "NO_TRADE";
  const msRemaining = signal.validUntil ? new Date(signal.validUntil).getTime() - now.getTime() : 0;
  const isAplusplus = signal.grade === "A++";
  const accent = signal.direction === "CALL" ? "bg-call" : signal.direction === "PUT" ? "bg-put" : "bg-notrade/70";
  // `now` is a prop (null-until-hydrated upstream), not Date.now(), so
  // server and client render identical markup.
  const lastChecked = signal.lastEvaluatedAt ?? signal.generatedAt;
  const checkStale = isCheckStale(lastChecked, now.getTime());

  return (
    <Card
      className={cn(
        "card-premium-hover overflow-hidden animate-in fade-in-0 slide-in-from-bottom-4 duration-500 ease-out",
        isAplusplus && "aplusplus-frame border-aplusplus/30"
      )}
      style={{ animationDelay: `${index * 90}ms` }}
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
            {/* A standing decision keeps ONE row -- `generatedAt` freezes while
                the engine keeps running. Without this line a healthy engine
                holding NO_TRADE for a day is indistinguishable from a dead
                one, and the natural response to that is to distrust the
                whole system (or to lower the quality bar until it speaks). */}
            <p className={cn("text-xs", checkStale ? "text-destructive" : "text-muted-foreground/70")}>
              {checkStale ? "Last checked " : "Checked "}
              {formatRelative(lastChecked, now.getTime())}
              {checkStale && ` — ${staleNote}`}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <RegimeBadge regime={signal.marketRegime} />
            {!isNoTrade && <GradeBadge grade={signal.grade} />}
          </div>
        </div>

        <DirectionBadge direction={signal.direction} className="text-sm" />

        {isNoTrade ? (
          <div className="rounded-md border border-dashed border-border bg-secondary/30 p-3">
            <p className="text-sm text-muted-foreground">
              {signal.warnings[0] ?? signal.reasons[0] ?? "Market conditions not strong enough for a signal."}
            </p>
            {signal.checks && signal.checks.length > 0 && (
              <div className="mt-3 border-t border-border/60 pt-3">
                <DecisionChecks checks={signal.checks} />
              </div>
            )}
          </div>
        ) : (
          <>
            <div className="grid grid-cols-2 gap-4 rounded-lg border border-border/70 bg-secondary/20 p-3.5 sm:grid-cols-4">
              <Metric label="Confidence" value={signal.confidence !== null ? <AnimatedNumber value={signal.confidence} suffix="%" /> : "N/A"} />
              <Metric label="Expiry" value={formatExpiry(expirySecondsOf(signal))} />
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
