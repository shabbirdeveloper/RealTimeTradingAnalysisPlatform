"use client";
import type { Signal, TimeframeBias } from "@/types";
import { cn, formatRelative, isCheckStale } from "@/lib/utils";

const ORDER = ["H4", "H1", "M15", "M5"] as const;

/**
 * The engine's current directional read, shown even -- especially -- when
 * the answer is NO TRADE.
 *
 * A card whose entire content is the words "NO TRADE" and a static
 * sentence is indistinguishable from a broken one, and it hides the fact
 * that the engine's view of the market is changing underneath. That
 * ambiguity is expensive: the reasonable reaction to "my dashboard never
 * changes" is to distrust it, or to lower the quality bar until it
 * speaks. Both are worse than seeing why the answer is no.
 *
 * So: the four timeframe biases, and how far the setup got toward the
 * quality bar. Nothing invented -- these are the same values the decision
 * was made from.
 */
export function MarketRead({ signal }: { signal: Signal }) {
  const byTimeframe = new Map<string, TimeframeBias>(
    (signal.timeframes ?? []).map((t) => [t.timeframe, t])
  );
  const agreement = agreementFor(signal.timeframes ?? []);
  const bar = requiredScore(signal);
  const pct = bar ? Math.min(100, Math.round((signal.technicalScore / bar) * 100)) : null;
  const lastChecked = signal.lastEvaluatedAt ?? signal.generatedAt;
  const stale = isCheckStale(lastChecked);

  return (
    <div className="space-y-2.5">
      <div className="flex items-center gap-1">
        {ORDER.map((tf) => {
          const read = byTimeframe.get(tf);
          const bias = read?.bias ?? "NEUTRAL";
          return (
            <div
              key={tf}
              title={read?.notes?.[0] ?? "No reading yet"}
              className={cn(
                "flex-1 rounded-md border px-1.5 py-1 text-center",
                bias === "BULLISH" && "border-call/30 bg-call-muted",
                bias === "BEARISH" && "border-put/30 bg-put-muted",
                bias === "NEUTRAL" && "border-border bg-secondary/40"
              )}
            >
              <p className="text-[9.5px] font-medium uppercase tracking-wider text-muted-foreground">{tf}</p>
              <p
                className={cn(
                  "text-[11px] font-semibold leading-tight",
                  bias === "BULLISH" && "text-call",
                  bias === "BEARISH" && "text-put",
                  bias === "NEUTRAL" && "text-muted-foreground"
                )}
              >
                {bias === "BULLISH" ? "Up" : bias === "BEARISH" ? "Down" : "Flat"}
              </p>
            </div>
          );
        })}
      </div>

      {pct !== null && (
        <div>
          <div className="flex items-baseline justify-between text-[10.5px]">
            <span className="font-medium uppercase tracking-wider text-muted-foreground">Setup quality</span>
            <span className="font-mono-tabular text-muted-foreground">
              {signal.technicalScore} / {bar}
            </span>
          </div>
          <div className="mt-1 h-1 w-full overflow-hidden rounded-full bg-secondary">
            <div
              className={cn("h-full rounded-full transition-all duration-500", pct >= 100 ? "bg-call" : "bg-notrade/70")}
              style={{ width: `${pct}%` }}
            />
          </div>
        </div>
      )}

      <p className="text-[10.5px] text-muted-foreground">
        {agreement}
        {" · "}
        <span className={cn(stale && "text-destructive")}>
          {stale ? "last checked " : "checked "}
          {formatRelative(lastChecked)}
        </span>
      </p>
    </div>
  );
}

function agreementFor(timeframes: TimeframeBias[]): string {
  if (timeframes.length === 0) return "No timeframe reading yet";
  const up = timeframes.filter((t) => t.bias === "BULLISH").length;
  const down = timeframes.filter((t) => t.bias === "BEARISH").length;
  const leading = Math.max(up, down);
  const side = up > down ? "up" : down > up ? "down" : "either way";
  if (leading === 0) return `0 of ${timeframes.length} timeframes committed`;
  return `${leading} of ${timeframes.length} ${side}`;
}

/**
 * The score this setup had to reach, taken from the engine's own recorded
 * check rather than duplicated here -- a threshold hardcoded in the UI
 * silently lies the moment the strategy config changes.
 */
function requiredScore(signal: Signal): number | null {
  const check = (signal.checks ?? []).find((c) => /setup quality/i.test(c.name));
  const parsed = check?.required ? Number(String(check.required).replace(/[^0-9.]/g, "")) : NaN;
  return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
}
