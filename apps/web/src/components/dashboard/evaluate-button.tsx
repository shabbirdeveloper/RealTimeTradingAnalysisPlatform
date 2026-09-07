"use client";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { SideMeter } from "@/components/dashboard/side-meter";
import { cn, formatExpiry } from "@/lib/utils";
import { Loader2, Minus, Play, TrendingDown, TrendingUp } from "lucide-react";

interface EvaluateResult {
  symbol: string;
  direction: string;
  isSignal: boolean;
  callScore: number | null;
  putScore: number | null;
  score: number | null;
  regime: string | null;
  regimeReason: string | null;
  strategy: string | null;
  entryPrice: number | null;
  expirySeconds: number | null;
  reasons: string[];
  warnings: string[];
  rejectionReasons: string[];
  barUnchanged: boolean;
}

/**
 * Runs the engine on demand.
 *
 * It runs the SAME evaluation the scheduler runs, on the same closed bars,
 * and shows whatever comes back — which is usually NO TRADE. That is the
 * point, and the UI says so, because the obvious failure mode of a button
 * like this is that it becomes a slot-machine handle: press until a CALL
 * appears, take that one, and throw away the selectivity that is the whole
 * product.
 *
 * `barUnchanged` is surfaced prominently for the same reason. When the
 * entry bar has not closed since the last evaluation the inputs are
 * identical, so the answer cannot change, and saying that outright is
 * cheaper than letting someone discover it by pressing twenty times.
 */
export function EvaluateButton({ symbol, label }: { symbol: string; label?: string }) {
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<EvaluateResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function run() {
    setBusy(true);
    setError(null);
    try {
      const response = await fetch(`/api/engine/evaluate?symbol=${encodeURIComponent(symbol)}`, {
        method: "POST",
      });
      const body = await response.json();
      if (!response.ok) {
        setError(body?.error ?? "The evaluation failed.");
        setResult(null);
      } else {
        setResult(body as EvaluateResult);
      }
    } catch {
      setError("The request could not be sent.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-3">
      <Button onClick={run} disabled={busy} className="w-full sm:w-auto">
        {busy ? (
          <>
            <Loader2 className="mr-2 h-4 w-4 animate-spin" /> Analysing {label ?? symbol}…
          </>
        ) : (
          <>
            <Play className="mr-2 h-4 w-4" /> Analyse {label ?? symbol} now
          </>
        )}
      </Button>

      {error && (
        <Card className="border-destructive/40">
          <CardContent className="p-4 text-sm text-destructive">{error}</CardContent>
        </Card>
      )}

      {result && <ResultCard result={result} />}
    </div>
  );
}

function ResultCard({ result }: { result: EvaluateResult }) {
  const call = result.direction === "CALL" && result.isSignal;
  const put = result.direction === "PUT" && result.isSignal;

  return (
    <Card className={cn(result.isSignal && (call ? "border-call/40" : "border-put/40"))}>
      <CardContent className="space-y-3.5 p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <span
            className={cn(
              "inline-flex items-center gap-1.5 text-base font-semibold",
              call ? "text-call" : put ? "text-put" : "text-notrade"
            )}
          >
            {call ? <TrendingUp className="h-4 w-4" /> : put ? <TrendingDown className="h-4 w-4" /> : <Minus className="h-4 w-4" />}
            {result.isSignal ? result.direction : "NO TRADE"}
          </span>
          {result.regime && (
            <Badge variant="outline" className="capitalize">
              {result.regime.replace(/_/g, " ").toLowerCase()}
            </Badge>
          )}
        </div>

        {result.barUnchanged && (
          /* The single most important line here. Without it, an unchanged
             answer reads as a broken button and invites pressing again. */
          <p className="rounded-md border border-dashed border-border bg-secondary/30 p-2.5 text-xs text-muted-foreground">
            The entry bar has not closed since the last evaluation, so the inputs
            are identical and this answer cannot change yet. Pressing again will
            return the same result.
          </p>
        )}

        {result.isSignal && (
          <div className="grid grid-cols-2 gap-3 text-sm">
            <div>
              <p className="text-[10.5px] uppercase tracking-wider text-muted-foreground">Entry</p>
              <p className="font-mono-tabular font-semibold text-foreground">
                {result.entryPrice?.toFixed(5) ?? "—"}
              </p>
            </div>
            <div>
              <p className="text-[10.5px] uppercase tracking-wider text-muted-foreground">Expiry</p>
              <p className="font-mono-tabular font-semibold text-foreground">
                {result.expirySeconds ? formatExpiry(result.expirySeconds) : "—"}
              </p>
            </div>
          </div>
        )}

        {result.callScore !== null && result.putScore !== null && (
          <SideMeter call={result.callScore} put={result.putScore} />
        )}

        {result.regimeReason && (
          <p className="text-xs text-muted-foreground">{result.regimeReason}</p>
        )}

        {result.rejectionReasons.length > 0 && (
          <div className="space-y-1">
            <p className="text-[10.5px] font-medium uppercase tracking-wider text-muted-foreground">
              Declined because
            </p>
            {result.rejectionReasons.map((r) => (
              <p key={r} className="text-xs text-foreground">{r}</p>
            ))}
          </div>
        )}

        {result.reasons.length > 0 && (
          <ul className="space-y-1">
            {result.reasons.slice(0, 6).map((r) => (
              <li key={r} className="text-xs text-muted-foreground">· {r}</li>
            ))}
          </ul>
        )}

        {result.warnings.map((w) => (
          <p key={w} className="text-xs text-notrade">! {w}</p>
        ))}
      </CardContent>
    </Card>
  );
}
