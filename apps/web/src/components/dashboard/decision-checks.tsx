import { Check, Minus, X } from "lucide-react";
import type { DecisionCheck } from "@/types";
import { cn } from "@/lib/utils";

/**
 * The gates a setup was put through, and where it stopped (spec Phase 26).
 *
 * A NO TRADE card used to carry one sentence — "Timeframes conflicting" —
 * which says what happened but not how close it came, which check was
 * responsible, or what would have had to be different. Those are the
 * questions someone actually has when they are looking at a card that never
 * seems to change.
 *
 * Checks after the failing one are shown greyed rather than hidden: the
 * engine genuinely stops at the first failure, and pretending it evaluated
 * the rest would be a more confident story than the truth.
 */
export function DecisionChecks({ checks }: { checks: DecisionCheck[] }) {
  if (!checks || checks.length === 0) return null;

  const stoppedAt = checks.findIndex((c) => !c.passed);

  return (
    <ul className="space-y-1.5">
      {checks.map((check, i) => {
        const isBlocker = i === stoppedAt;
        const notReached = stoppedAt !== -1 && i > stoppedAt;

        return (
          <li
            key={check.name}
            className={cn(
              "flex items-start gap-2 text-xs",
              notReached && "opacity-40"
            )}
          >
            <span className="mt-0.5 shrink-0">
              {notReached ? (
                <Minus className="h-3.5 w-3.5 text-muted-foreground" />
              ) : check.passed ? (
                <Check className="h-3.5 w-3.5 text-call" />
              ) : (
                <X className="h-3.5 w-3.5 text-put" />
              )}
            </span>

            <span className="min-w-0 flex-1">
              <span
                className={cn(
                  "font-medium",
                  isBlocker ? "text-put" : "text-foreground"
                )}
              >
                {check.name}
              </span>

              {check.value && (
                <span className="ml-1.5 font-mono-tabular text-muted-foreground">
                  {check.value}
                  {check.required && ` · needs ${check.required}`}
                </span>
              )}

              {/* The detail earns its space on the blocker and nowhere else —
                  repeating it on every passing row buries the one that matters. */}
              {isBlocker && (
                <span className="mt-0.5 block text-muted-foreground">{check.detail}</span>
              )}
            </span>
          </li>
        );
      })}

      {stoppedAt === -1 && (
        <li className="pt-1 text-xs text-muted-foreground">
          Every check passed — this setup was taken.
        </li>
      )}
    </ul>
  );
}
