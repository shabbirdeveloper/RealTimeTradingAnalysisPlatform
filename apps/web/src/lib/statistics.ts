/**
 * Statistical honesty for accuracy figures (spec section 15: never claim an
 * accuracy the results don't actually demonstrate).
 *
 * A bare "71.4%" is the most misleading number this platform could show. Over
 * 14 resolved signals it means almost nothing; over 1,400 it means a great
 * deal. Showing the interval alongside it is the difference between a real
 * measurement and a marketing figure.
 */

/**
 * Wilson score interval — the standard choice for binomial proportions at
 * small n, where the naive normal approximation badly misbehaves (it can
 * even produce bounds below 0% or above 100%).
 *
 * Verified against an independent Python implementation: 60/100 → 50.2%-69.1%,
 * 300/500 → 55.6%-64.2%, 12/20 → 38.7%-78.1%.
 */
export function wilsonInterval(wins: number, total: number, z = 1.96): { low: number; high: number } {
  if (total <= 0) return { low: 0, high: 0 };
  const p = wins / total;
  const denominator = 1 + (z * z) / total;
  const centre = (p + (z * z) / (2 * total)) / denominator;
  const halfWidth =
    (z / denominator) * Math.sqrt((p * (1 - p)) / total + (z * z) / (4 * total * total));
  return {
    low: Math.max(0, (centre - halfWidth) * 100),
    high: Math.min(100, (centre + halfWidth) * 100),
  };
}

/**
 * The win rate at which a binary trade breaks even: a win pays `payout` times
 * the stake, a loss costs the whole stake.
 *
 *     p × payout = (1 − p) × 1   →   p = 1 / (1 + payout)
 *
 * This is the number that actually matters. At a typical 80% payout you need
 * 55.6% just to stop losing money — so a "60% accurate" system is far closer
 * to break-even than it sounds, and a 55% one loses.
 */
export function breakEvenWinRate(payoutPercent: number): number {
  const payout = payoutPercent / 100;
  if (payout <= 0) return 100;
  return (1 / (1 + payout)) * 100;
}

export type EvidenceVerdict =
  | { kind: "none"; message: string }
  | { kind: "insufficient"; message: string }
  | { kind: "below"; message: string }
  | { kind: "unproven"; message: string }
  | { kind: "above"; message: string };

/**
 * Plain-language reading of what the sample does and doesn't establish,
 * relative to the break-even rate for the user's actual payout.
 */
export function assessEvidence(
  wins: number,
  losses: number,
  payoutPercent: number
): EvidenceVerdict {
  const total = wins + losses;
  if (total === 0) {
    return { kind: "none", message: "No resolved signals yet — there is nothing to measure." };
  }

  const breakEven = breakEvenWinRate(payoutPercent);
  const { low, high } = wilsonInterval(wins, total);
  const observed = (wins / total) * 100;

  if (total < 30) {
    return {
      kind: "insufficient",
      message:
        `${total} resolved signal${total === 1 ? "" : "s"} is far too few to conclude anything. ` +
        `The true rate could plausibly be anywhere from ${low.toFixed(0)}% to ${high.toFixed(0)}%.`,
    };
  }

  if (high < breakEven) {
    return {
      kind: "below",
      message:
        `Even the optimistic end of the range (${high.toFixed(1)}%) sits below the ${breakEven.toFixed(1)}% ` +
        `needed to break even at a ${payoutPercent}% payout. On this evidence the strategy loses money.`,
    };
  }

  if (low > breakEven) {
    return {
      kind: "above",
      message:
        `The whole plausible range (${low.toFixed(1)}%–${high.toFixed(1)}%) sits above the ` +
        `${breakEven.toFixed(1)}% break-even for a ${payoutPercent}% payout, across ${total} resolved signals.`,
    };
  }

  return {
    kind: "unproven",
    message:
      `Observed ${observed.toFixed(1)}%, but the range (${low.toFixed(1)}%–${high.toFixed(1)}%) still straddles ` +
      `the ${breakEven.toFixed(1)}% break-even for a ${payoutPercent}% payout — so this does not yet show ` +
      `profitability either way. More resolved signals are needed.`,
  };
}

/**
 * Roughly how many resolved signals are needed before the lower bound of the
 * interval clears break-even, assuming the observed rate holds. Returns null
 * when the observed rate is at or below break-even, where no sample size helps.
 *
 * The answers are sobering and worth surfacing: sustaining 60% against an 80%
 * payout needs ~490 resolved signals; 65% needs ~110; 70% needs ~50.
 */
export function signalsNeededToProve(
  observedRate: number,
  payoutPercent: number,
  maxN = 20000
): number | null {
  const breakEven = breakEvenWinRate(payoutPercent);
  if (observedRate <= breakEven) return null;
  for (let n = 10; n <= maxN; n += 10) {
    const { low } = wilsonInterval(Math.round((observedRate / 100) * n), n);
    if (low > breakEven) return n;
  }
  return null;
}

export const DEFAULT_PAYOUT_PERCENT = 80;
