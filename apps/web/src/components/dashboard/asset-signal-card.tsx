"use client";
import Link from "next/link";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { DirectionBadge, GradeBadge, RegimeBadge, DataStatusPill } from "@/components/shared/badges";
import { Badge } from "@/components/ui/badge";
import { AnimatedNumber } from "@/components/shared/animated-number";
import { PriceTicker } from "@/components/shared/price-ticker";
import { ASSET_CONFIGS } from "@/data/assets";
import type { DataStatus, Signal } from "@/types";
import { cn, expirySecondsOf, formatExpiry, formatPercent, formatPrice } from "@/lib/utils";
import { ArrowUpRight, ArrowDownRight, Minus, PauseCircle } from "lucide-react";
import { MarketRead } from "@/components/dashboard/market-read";
import { MarketClosedNotice } from "@/components/dashboard/market-closed-notice";
import { isMarketOpen } from "@/lib/market-hours";
import { useNow } from "@/lib/use-now";

export function AssetSignalCard({
  signal,
  price,
  change24hPct,
  index = 0,
  regimeAvailable = true,
  dataStatus,
  lastEvaluatedAt,
}: {
  signal: Signal;
  price: number;
  change24hPct: number;
  index?: number;
  /** False when no real regime classification exists yet (Phase 3 not
   * built) -- shows a neutral "Not analyzed" badge instead of a
   * MarketRegime value that would otherwise have to be fabricated. */
  regimeAvailable?: boolean;
  /** Freshness of the underlying price data, per spec section 42. Only
   * rendered when provided -- demo-data callers can omit it. */
  dataStatus?: DataStatus;
  /** Newest decision of any status — see getLastEvaluationTimes(). */
  lastEvaluatedAt?: string | null;
}) {
  const cfg = ASSET_CONFIGS[signal.asset];
  // Null until hydration, so the server renders the ordinary card and the
  // closed state appears client-side. Getting this backwards would mean SSR
  // asserting "closed" from the server's clock, which is not the viewer's.
  const now = useNow(30_000);
  const closed = now !== null && !isMarketOpen(signal.asset, now);
  const isNoTrade = signal.direction === "NO_TRADE";
  const isAplusplus = signal.grade === "A++";
  // Spec section 42. The STALE pill in the corner was the only thing saying
  // this data was old, while the body went on showing PUT, a grade and a
  // best expiry -- which is a tradeable instruction. A pill does not undo a
  // direction badge; a reader takes the loudest element on the card, and the
  // loudest element was the trade.
  const actionable = !dataStatus || dataStatus === "LIVE" || dataStatus === "DELAYED";

  const accent =
    signal.direction === "CALL" ? "bg-call" : signal.direction === "PUT" ? "bg-put" : "bg-notrade/70";

  return (
    <Link href={`/dashboard/markets/${signal.asset.toLowerCase()}`} className="rise-in block" style={{ animationDelay: `${index * 70}ms` }}>
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
          <div className="flex flex-col items-end gap-1.5">
            {regimeAvailable ? (
              <RegimeBadge regime={signal.marketRegime} />
            ) : (
              <Badge variant="outline" className="text-muted-foreground">Not analyzed</Badge>
            )}
            {dataStatus && !closed && <DataStatusPill status={dataStatus} />}
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-baseline justify-between">
            <PriceTicker
              value={price}
              decimals={cfg.pipDecimal}
              className="text-[27px] font-semibold leading-none tracking-[-0.02em] text-foreground"
            />
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

          {closed ? (
            <MarketClosedNotice asset={signal.asset} />
          ) : !actionable ? (
            <div className="space-y-2 rounded-md border border-dashed border-notrade/40 bg-notrade/5 p-3">
              <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-notrade">
                <PauseCircle className="h-3.5 w-3.5" /> Signal generation paused
              </span>
              <p className="text-xs leading-relaxed text-muted-foreground">
                {dataStatus === "OFFLINE"
                  ? "No recent candle has arrived, so nothing here is current. The price above is the last one recorded."
                  : "The last decision is too old to act on. The price above is the last one recorded, not a live quote."}
              </p>
            </div>
          ) : isNoTrade ? (
            <div className="space-y-3 rounded-md border border-dashed border-border bg-secondary/30 p-3">
              <DirectionBadge direction="NO_TRADE" />
              <p className="text-xs leading-relaxed text-muted-foreground">
                {signal.warnings[0] ?? signal.reasons[0] ?? "Market conditions not strong enough."}
              </p>
              {/* Without this the card is a static word. The engine's read
                  moves every cycle even when the answer stays no, and
                  hiding that makes a working system look frozen. */}
              <MarketRead signal={signal} lastEvaluatedAt={lastEvaluatedAt} />
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
                    {signal.confidence !== null ? (
                      <AnimatedNumber value={signal.confidence} suffix="%" />
                    ) : (
                      "Not available"
                    )}
                  </p>
                </div>
                <div className="text-right">
                  <p className="text-[10.5px] font-medium uppercase tracking-wider text-muted-foreground">Best expiry</p>
                  <p className="font-mono-tabular text-lg font-semibold text-foreground">{formatExpiry(expirySecondsOf(signal))}</p>
                </div>
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </Link>
  );
}
