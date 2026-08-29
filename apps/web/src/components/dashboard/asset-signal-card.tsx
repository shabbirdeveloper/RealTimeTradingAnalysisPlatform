"use client";
import Link from "next/link";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { DirectionBadge, GradeBadge, RegimeBadge } from "@/components/shared/badges";
import { ASSET_CONFIGS } from "@/data/assets";
import type { Signal } from "@/types";
import { formatPrice, formatPercent, cn } from "@/lib/utils";
import { ArrowUpRight, ArrowDownRight, Minus } from "lucide-react";

export function AssetSignalCard({ signal, price, change24hPct }: { signal: Signal; price: number; change24hPct: number }) {
  const cfg = ASSET_CONFIGS[signal.asset];
  const isNoTrade = signal.direction === "NO_TRADE";
  const isAplusplus = signal.grade === "A++";

  const accent =
    signal.direction === "CALL" ? "bg-call" : signal.direction === "PUT" ? "bg-put" : "bg-notrade/70";

  return (
    <Link href={`/dashboard/markets/${signal.asset.toLowerCase()}`} className="block">
      <Card
        className={cn(
          "card-premium-hover h-full overflow-hidden",
          isAplusplus && "aplusplus-frame border-aplusplus/30"
        )}
      >
        <div className={cn("h-[3px] w-full", accent)} />
        <CardHeader className="flex-row items-start justify-between space-y-0 pb-3 pt-4">
          <div>
            <p className="text-sm font-semibold text-foreground">{cfg.displayName}</p>
            <p className="text-xs text-muted-foreground">{cfg.shortName}</p>
          </div>
          <RegimeBadge regime={signal.marketRegime} />
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-baseline justify-between">
            <span className="font-mono-tabular text-[26px] font-semibold leading-none tracking-tight text-foreground">
              {formatPrice(price, cfg.pipDecimal)}
            </span>
            <span
              className={cn(
                "flex items-center gap-0.5 rounded-md px-1.5 py-0.5 font-mono-tabular text-xs font-semibold",
                change24hPct > 0 ? "bg-call-muted text-call" : change24hPct < 0 ? "bg-put-muted text-put" : "text-muted-foreground"
              )}
            >
              {change24hPct > 0 ? <ArrowUpRight className="h-3 w-3" /> : change24hPct < 0 ? <ArrowDownRight className="h-3 w-3" /> : <Minus className="h-3 w-3" />}
              {formatPercent(Math.abs(change24hPct))}
            </span>
          </div>

          {isNoTrade ? (
            <div className="rounded-md border border-dashed border-border bg-secondary/30 p-3">
              <DirectionBadge direction="NO_TRADE" />
              <p className="mt-2 text-xs leading-relaxed text-muted-foreground">
                {signal.warnings[0] ?? signal.reasons[0] ?? "Market conditions not strong enough."}
              </p>
            </div>
          ) : (
            <div className="space-y-3 border-t border-border/70 pt-3.5">
              <div className="flex items-center justify-between">
                <DirectionBadge direction={signal.direction} />
                <GradeBadge grade={signal.grade} />
              </div>
              <div className="flex items-end justify-between">
                <div>
                  <p className="text-[10.5px] font-medium uppercase tracking-wider text-muted-foreground">Confidence</p>
                  <p className="font-mono-tabular text-lg font-semibold text-foreground">
                    {signal.confidence !== null ? formatPercent(signal.confidence) : "Not available"}
                  </p>
                </div>
                <div className="text-right">
                  <p className="text-[10.5px] font-medium uppercase tracking-wider text-muted-foreground">Best expiry</p>
                  <p className="font-mono-tabular text-lg font-semibold text-foreground">{signal.expiryMinutes} min</p>
                </div>
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </Link>
  );
}
