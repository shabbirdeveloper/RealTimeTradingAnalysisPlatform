"use client";
import { useEffect } from "react";
import { useRouter } from "next/navigation";

/**
 * Re-fetches the page's server data on an interval.
 *
 * The dashboard is a server component rendered per request, so without this
 * it is a photograph: the engine decides every couple of minutes and the
 * page keeps showing whatever it showed when it was opened. A countdown
 * running to zero next to a signal that never changes is worse than no
 * countdown at all -- it says something is about to happen and then nothing
 * does.
 *
 * router.refresh() re-runs the server components and swaps in the new data
 * without a full page load, so scroll position and client state survive.
 *
 * Paused while the tab is hidden. A dashboard left open in a background tab
 * for a day would otherwise make thousands of pointless round trips, and
 * the moment it becomes visible again it refreshes once, which is the only
 * refresh that mattered.
 */
export function AutoRefresh({ intervalMs = 30_000 }: { intervalMs?: number }) {
  const router = useRouter();

  useEffect(() => {
    let timer: ReturnType<typeof setInterval> | null = null;

    const start = () => {
      if (timer !== null) return;
      timer = setInterval(() => router.refresh(), intervalMs);
    };
    const stop = () => {
      if (timer === null) return;
      clearInterval(timer);
      timer = null;
    };

    const onVisibility = () => {
      if (document.hidden) {
        stop();
      } else {
        router.refresh();
        start();
      }
    };

    if (!document.hidden) start();
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      stop();
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [router, intervalMs]);

  return null;
}
