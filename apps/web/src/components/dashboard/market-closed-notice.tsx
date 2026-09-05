"use client";
import { CalendarClock } from "lucide-react";
import { useNow } from "@/lib/use-now";
import { nextOpen, timeUntilOpen } from "@/lib/market-hours";
import type { AssetSymbol } from "@/types";
import { cn } from "@/lib/utils";

/**
 * Shown in place of a signal when the instrument's market is shut.
 *
 * The alternative was to leave the card showing Friday's last decision, which
 * is what it did before: a price that has not moved for a day, a STALE pill,
 * and nothing saying why. That reads as a broken platform. It is also the one
 * place where a platform is most tempted to invent a price, which spec
 * section 50 forbids outright — so the honest answer is to say the market is
 * closed and when it opens, and to point at what is actually tradeable now.
 */
export function MarketClosedNotice({
  asset,
  className,
}: {
  asset: AssetSymbol;
  className?: string;
}) {
  const now = useNow(30_000);

  // useNow is null until after hydration, so render the sentence without the
  // countdown rather than a number the server and client would disagree on.
  const until = now ? timeUntilOpen(asset, now) : null;
  const open = now ? nextOpen(asset, now) : null;

  return (
    <div
      className={cn(
        "space-y-2 rounded-md border border-dashed border-border bg-secondary/30 p-3",
        className
      )}
    >
      <span className="inline-flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
        <CalendarClock className="h-3.5 w-3.5" /> Market closed
      </span>
      <p className="text-xs leading-relaxed text-muted-foreground">
        Forex is shut over the weekend, so there is no price to analyse. The last
        figure above is Friday&rsquo;s close, not a live quote.
      </p>
      {open && (
        <p className="text-xs text-muted-foreground">
          Opens{" "}
          <span className="font-medium text-foreground">
            {open.toLocaleString(undefined, {
              weekday: "short",
              hour: "2-digit",
              minute: "2-digit",
            })}
          </span>
          {until && <span className="font-mono-tabular"> · in {until}</span>}
        </p>
      )}
    </div>
  );
}
