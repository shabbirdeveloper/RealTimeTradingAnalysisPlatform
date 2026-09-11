/**
 * The gate a setup has to clear before it becomes a signal.
 *
 * MIRRORS `minimum_score` in apps/api/app/otc/config.py. The engine decides;
 * this copy exists only so the UI can draw the score against the bar it was
 * judged by. Change both together — a UI showing 81/78 while the engine
 * refuses at 85 is worse than showing no bar at all.
 *
 * The number is NOT yet evidence-backed. It was chosen, not measured, and
 * whether it is reachable at all is what otc_backtest.py --sweep exists to
 * answer. Until that runs it is an honest placeholder, which is why nothing
 * in this codebase presents it as a validated accuracy figure.
 */
export const SCORE_FLOOR = 78;
