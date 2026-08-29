"use client";
import { useEffect, useRef, useState } from "react";

/**
 * Animates a numeric value counting up/down to its target whenever it
 * changes, including the very first mount (starts from 0). Purely visual —
 * never invents a number, just eases the transition to whatever value the
 * caller already computed (e.g. from the signal engine or static demo data).
 */
export function AnimatedNumber({
  value,
  decimals = 1,
  suffix = "",
  prefix = "",
  duration = 700,
  className,
}: {
  value: number;
  decimals?: number;
  suffix?: string;
  prefix?: string;
  duration?: number;
  className?: string;
}) {
  const [display, setDisplay] = useState(0);
  const prevValue = useRef(0);
  const frameRef = useRef<number | undefined>(undefined);

  useEffect(() => {
    const from = prevValue.current;
    const to = value;
    if (from === to) {
      setDisplay(to);
      return;
    }
    const start = performance.now();

    function tick(now: number) {
      const progress = Math.min(1, (now - start) / duration);
      const eased = 1 - Math.pow(1 - progress, 3);
      setDisplay(from + (to - from) * eased);
      if (progress < 1) {
        frameRef.current = requestAnimationFrame(tick);
      } else {
        prevValue.current = to;
      }
    }

    frameRef.current = requestAnimationFrame(tick);
    return () => {
      if (frameRef.current !== undefined) cancelAnimationFrame(frameRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value, duration]);

  return (
    <span className={className}>
      {prefix}
      {display.toFixed(decimals)}
      {suffix}
    </span>
  );
}
