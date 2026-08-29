"use client";
import { useEffect, useState } from "react";

/**
 * Returns null on the server and on the first client render (so SSR output
 * matches hydration exactly), then starts ticking a real Date client-side
 * only. Components that need a "live" clock for demo countdowns/timestamps
 * should render a skeleton while this is null.
 */
export function useNow(tickMs = 1000): Date | null {
  const [now, setNow] = useState<Date | null>(null);

  useEffect(() => {
    setNow(new Date());
    const id = setInterval(() => setNow(new Date()), tickMs);
    return () => clearInterval(id);
  }, [tickMs]);

  return now;
}
