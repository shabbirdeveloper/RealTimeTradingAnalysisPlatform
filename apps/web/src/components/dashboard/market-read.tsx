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
export function MarketRead({
  signal,
  lastEvaluatedAt,
}: {
  signal: Signal;
  /** From latest_evaluation_times(): the newest decision of ANY status.
   *  May be far newer than this signal, because REJECTED decisions are
   *  hidden from non-admins. */
  lastEvaluatedAt?: string | null;
}) {
  const byTimeframe = new Map<string, TimeframeBias>(
    (signal.timeframes ?? []).map((t) => [t.timeframe, t])
  );
  const agreement = agreementFor(signal.timeframes ?? []);
  const bar = requiredScore(signal);
  const pct = bar ? Math.min(100, Math.round((signal.technicalScore / bar) * 100)) : null;
  const shownAt = signal.lastEvaluatedAt ?? signal.generatedAt;
  // Prefer the engine's real last look. When the newest decision is one the
  // reader may not see, `shownAt` lags it and the card would otherwise
  // accuse a healthy engine of having stopped.
  const lastChecked =
    lastEvaluatedAt && new Date(lastEvaluatedAt) > new Date(shownAt) ? lastEvaluatedAt : shownAt;
  const stale = isCheckStale(lastChecked);
  const hiddenNewer = Boolean(lastEvaluatedAt && new Date(lastEvaluatedAt) > new Date(shownAt));

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

      {/* CALL against PUT, scored from the same evidence and neither derived
          from the other. The bars deliberately do not fill the row: the space
          left over is evidence nobody committed, which is a different state
          from the two sides being balanced. */}
      {signal.callScore != null && signal.putScore != null && (
        <div className="space-y-1">
          <SideBar label="Call" value={signal.callScore} tone="call" />
          <SideBar label="Put" value={signal.putScore} tone="put" />
        </div>
      )}

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
        {signal.callScore != null && signal.putScore != null
          ? `${Math.abs(signal.callScore - signal.putScore)} apart · ${agreement}`
          : agreement}
        {" · "}
        <span className={cn(stale && "text-destructive")}>
          {stale ? "last checked " : "checked "}
          {formatRelative(lastChecked)}
        </span>
        {hiddenNewer && (
          <span className="text-muted-foreground">
            {" · current read is a rejected setup"}
          </span>
        )}
      </p>
    </div>
  );
}

function SideBar({ label, value, tone }: { label: string; value: number; tone: "call" | "put" }) {
  return (
    <div className="flex items-center gap-2">
      <span className="w-7 shrink-0 text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
        {label}
      </span>
      <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-secondary">
        <div
          className={cn("h-full rounded-full transition-all duration-500", tone === "call" ? "bg-call" : "bg-put")}
          style={{ width: `${Math.max(0, Math.min(100, value))}%` }}
        />
      </div>
      <span
        className={cn(
          "w-6 shrink-0 text-right font-mono-tabular text-[11px] font-semibold",
          tone === "call" ? "text-call" : "text-put"
        )}
      >
        {value}
      </span>
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
