"use client";
import { useEffect, useState } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  assessEvidence, breakEvenWinRate, signalsNeededToProve, wilsonInterval,
  DEFAULT_PAYOUT_PERCENT,
} from "@/lib/statistics";
import { CircleAlert, CircleCheck, CircleHelp, Info } from "lucide-react";

const PAYOUT_KEY = "northfx.payout-percent";

/**
 * Turns a bare win rate into an honest measurement (spec section 15).
 *
 * Two things a raw percentage hides, both shown here:
 *  1. Sample size. 60% over 20 signals and 60% over 2,000 are wildly
 *     different claims; the confidence interval makes that visible.
 *  2. The bar that actually matters. A binary win pays less than it risks,
 *     so break-even is ~55.6% at an 80% payout -- "60% accurate" is much
 *     closer to losing money than it sounds.
 *
 * The payout is user-set because it's broker- and asset-specific, and it
 * changes the verdict entirely. Stored locally; it's a display preference,
 * not account data.
 */
export function AccuracyVerdict({ wins, losses }: { wins: number; losses: number }) {
  const [payout, setPayout] = useState(DEFAULT_PAYOUT_PERCENT);

  useEffect(() => {
    try {
      const stored = localStorage.getItem(PAYOUT_KEY);
      if (stored) {
        const value = Number(stored);
        if (Number.isFinite(value) && value > 0 && value <= 100) setPayout(value);
      }
    } catch {
      // Storage blocked -- the default is fine.
    }
  }, []);

  const updatePayout = (value: number) => {
    setPayout(value);
    try {
      localStorage.setItem(PAYOUT_KEY, String(value));
    } catch {
      // Non-essential.
    }
  };

  const total = wins + losses;
  const observed = total > 0 ? (wins / total) * 100 : 0;
  const { low, high } = wilsonInterval(wins, total);
  const breakEven = breakEvenWinRate(payout);
  const verdict = assessEvidence(wins, losses, payout);
  const needed = total > 0 ? signalsNeededToProve(observed, payout) : null;

  const tone =
    verdict.kind === "above" ? "call" : verdict.kind === "below" ? "put" : "notrade";
  const Icon =
    verdict.kind === "above" ? CircleCheck : verdict.kind === "below" ? CircleAlert : CircleHelp;

  return (
    <Card>
      <CardContent className="space-y-4 p-5">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <p className="text-[10.5px] font-medium uppercase tracking-wider text-muted-foreground">
              Measured win rate
            </p>
            {total === 0 ? (
              <p className="font-mono-tabular text-2xl font-semibold text-muted-foreground">—</p>
            ) : (
              <>
                <p className="font-mono-tabular text-2xl font-semibold text-foreground">
                  {observed.toFixed(1)}%
                </p>
                <p className="font-mono-tabular text-xs text-muted-foreground">
                  95% confidence: {low.toFixed(1)}% – {high.toFixed(1)}% · {total} resolved
                </p>
              </>
            )}
          </div>
          <div className="w-36 space-y-1.5">
            <Label htmlFor="payout" className="text-xs">Your broker payout %</Label>
            <Input
              id="payout"
              type="number"
              min={1}
              max={100}
              value={payout}
              onChange={(e) => updatePayout(Number(e.target.value))}
            />
            <p className="text-[11px] text-muted-foreground">
              Break-even: <span className="font-mono-tabular">{breakEven.toFixed(1)}%</span>
            </p>
          </div>
        </div>

        {total > 0 && <IntervalBar low={low} high={high} breakEven={breakEven} />}

        <div
          className={`flex items-start gap-2.5 rounded-md border px-3.5 py-2.5 text-xs ${
            tone === "call"
              ? "border-call/30 bg-call-muted/40 text-call-foreground"
              : tone === "put"
                ? "border-put/30 bg-put-muted/40 text-put-foreground"
                : "border-notrade/30 bg-notrade-muted/40 text-notrade-foreground"
          }`}
        >
          <Icon className="mt-0.5 h-4 w-4 shrink-0" />
          <span>{verdict.message}</span>
        </div>

        {needed !== null && verdict.kind !== "above" && (
          <p className="flex items-start gap-2 text-xs text-muted-foreground">
            <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" />
            <span>
              If {observed.toFixed(0)}% holds up, it would take roughly{" "}
              <strong className="font-semibold text-foreground">{needed} resolved signals</strong> before that rate
              is statistically distinguishable from break-even. You have {total}.
            </span>
          </p>
        )}

        <p className="border-t border-border pt-3 text-[11px] leading-relaxed text-muted-foreground">
          Win rate measures direction only. It does not account for spread, execution delay between the signal and
          your click, or the exact expiry price your broker settles on — all of which make real results somewhat
          worse than measured.
        </p>
      </CardContent>
    </Card>
  );
}

/** Visual: where the plausible range sits relative to break-even. */
function IntervalBar({ low, high, breakEven }: { low: number; high: number; breakEven: number }) {
  return (
    <div className="space-y-1.5">
      <div className="relative h-2 w-full rounded-full bg-secondary">
        <div
          className="absolute h-2 rounded-full bg-primary/70"
          style={{ left: `${low}%`, width: `${Math.max(high - low, 0.5)}%` }}
        />
        <div
          className="absolute -top-1 h-4 w-0.5 bg-notrade"
          style={{ left: `${breakEven}%` }}
          title={`Break-even ${breakEven.toFixed(1)}%`}
        />
      </div>
      <div className="flex justify-between text-[10px] text-muted-foreground">
        <span>0%</span>
        <span>plausible range vs break-even marker</span>
        <span>100%</span>
      </div>
    </div>
  );
}
