"use client";
import { useState } from "react";
import Link from "next/link";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn, formatExpiry, formatRelative, isCheckStale } from "@/lib/utils";
import type { PreviewRow } from "@/lib/public-preview";
import { OTC_ASSET_LIST } from "@/data/assets";
import type { OtcAssetSymbol } from "@/types";
import { FlaskConical, Lock, Minus, Radio } from "lucide-react";

/**
 * A synthetic index is broker-generated, not a real market. Spec section 72
 * forbids mixing the two, and a tab strip that lists "Volatility 75" beside
 * "EUR/USD" with nothing between them is exactly that mixing in its quietest
 * form: the visitor assumes both are markets because the UI never said
 * otherwise. The marker is here, not only on the detail body, because the
 * strip is what someone reads before clicking anything.
 */
function isSynthetic(symbol: string): boolean {
  return OTC_ASSET_LIST.includes(symbol as OtcAssetSymbol);
}

/**
 * The engine, live, on the public page.
 *
 * Every figure here is a real decision the engine actually reached — this
 * is not a simulator. Two consequences, both deliberate:
 *
 * Most of the time it will say NO TRADE, and that is shown in full rather
 * than skipped past. "Most cycles end in no trade" is the platform's
 * actual thesis; a preview that only ever displayed signals would
 * misrepresent the product in the flattering direction, which is the
 * failure mode of every signal-service landing page.
 *
 * When a real signal DOES exist, the direction is withheld — the server
 * function never sends it. A visitor sees that one is there and what
 * quality it reached, not which way to trade.
 */
export function SignalPreview({ rows }: { rows: PreviewRow[] }) {
  const [active, setActive] = useState(0);

  if (rows.length === 0) {
    return (
      <Card className="border-dashed">
        <CardContent className="p-6 text-sm text-muted-foreground">
          The engine has not published a decision yet. This panel shows real output
          only — there is no simulated fallback.
        </CardContent>
      </Card>
    );
  }

  const row = rows[Math.min(active, rows.length - 1)]!;
  const stale = isCheckStale(row.lastEvaluatedAt, Date.now(), 30);
  const bar = 78;

  return (
    <Card className="overflow-hidden">
      <div className="flex flex-wrap gap-1 border-b border-border bg-secondary/30 p-1.5">
        {rows.map((r, i) => (
          <button
            key={r.symbol}
            onClick={() => setActive(i)}
            className={cn(
              "rounded px-2.5 py-1 text-xs font-medium transition-colors",
              i === active
                ? "bg-background text-foreground shadow-sm"
                : "text-muted-foreground hover:text-foreground"
            )}
          >
            <span className="inline-flex items-center gap-1">
              {isSynthetic(r.symbol) && <FlaskConical className="h-3 w-3 text-notrade" />}
              {r.displayName}
            </span>
          </button>
        ))}
      </div>

      <CardContent className="space-y-4 p-5">
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="flex items-center gap-1.5 text-sm font-semibold text-foreground">
              {row.displayName}
              {isSynthetic(row.symbol) && (
                <span className="inline-flex items-center gap-1 rounded border border-notrade/40 bg-notrade/10 px-1.5 py-0.5 text-[9.5px] font-medium uppercase tracking-wider text-notrade">
                  <FlaskConical className="h-2.5 w-2.5" /> Synthetic
                </span>
              )}
            </p>
            <p className={cn("text-xs", stale ? "text-destructive" : "text-muted-foreground")}>
              {stale ? "last checked " : "checked "}
              {formatRelative(row.lastEvaluatedAt)}
            </p>
          </div>
          {row.marketRegime && (
            <Badge variant="outline" className="capitalize">
              {row.marketRegime.replace(/_/g, " ").toLowerCase()}
            </Badge>
          )}
        </div>

        {row.hasSignal ? (
          <div className="space-y-3 rounded-md border border-primary/30 bg-primary/5 p-3.5">
            <div className="flex items-center justify-between">
              <span className="inline-flex items-center gap-1.5 text-sm font-semibold text-primary">
                <Radio className="h-3.5 w-3.5" /> Signal open
              </span>
              {row.grade && <Badge>{row.grade}</Badge>}
            </div>
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Lock className="h-3.5 w-3.5 shrink-0" />
              Direction and entry are for signed-in members.
            </div>
            {row.expirySeconds !== null && (
              <p className="text-xs text-muted-foreground">
                Expiry {formatExpiry(row.expirySeconds)} · quality {row.technicalScore}/100
              </p>
            )}
          </div>
        ) : (
          <div className="space-y-3 rounded-md border border-dashed border-border bg-secondary/30 p-3.5">
            <span className="inline-flex items-center gap-1.5 text-sm font-semibold text-notrade">
              <Minus className="h-3.5 w-3.5" /> No trade
            </span>
            <p className="text-xs leading-relaxed text-muted-foreground">
              Conditions did not clear the bar. This is the normal result — the engine
              declines far more often than it signals.
            </p>
          </div>
        )}

        {row.callScore !== null && row.putScore !== null && (
          <div className="space-y-1.5">
            <Side label="Call" value={row.callScore} tone="call" />
            <Side label="Put" value={row.putScore} tone="put" />
            <p className="pt-0.5 text-[10.5px] text-muted-foreground">
              Scored independently — both are low when the evidence is thin, which is
              why they need not add to 100.
            </p>
          </div>
        )}

        {row.technicalScore !== null && (
          <div>
            <div className="flex items-baseline justify-between text-[10.5px]">
              <span className="font-medium uppercase tracking-wider text-muted-foreground">
                Setup quality
              </span>
              <span className="font-mono-tabular text-muted-foreground">
                {row.technicalScore} / {bar}
              </span>
            </div>
            <div className="mt-1 h-1 w-full overflow-hidden rounded-full bg-secondary">
              <div
                className={cn(
                  "h-full rounded-full transition-all duration-500",
                  row.technicalScore >= bar ? "bg-call" : "bg-notrade/70"
                )}
                style={{ width: `${Math.min(100, (row.technicalScore / bar) * 100)}%` }}
              />
            </div>
          </div>
        )}

        {isSynthetic(row.symbol) && (
          <p className="rounded-md border border-dashed border-notrade/30 bg-notrade/5 p-2.5 text-[10.5px] leading-relaxed text-muted-foreground">
            A broker-generated volatility index, not a real market. Its prices come
            from Deriv&rsquo;s own random generator, so it runs 24/7 and no economic
            news moves it. Results on it are tracked separately from real-market
            instruments and never pooled with them.
          </p>
        )}

        <Link href="/register" className="block">
          <Button className="w-full">Create an account to see directions</Button>
        </Link>
      </CardContent>
    </Card>
  );
}

function Side({ label, value, tone }: { label: string; value: number; tone: "call" | "put" }) {
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
