"use client";
import { useEffect, useRef, useState } from "react";
import { cn, formatPrice } from "@/lib/utils";

/**
 * A price that shows its last move.
 *
 * The number alone cannot say which way it just went — a re-render looks
 * identical whether the price rose or fell. The flash is the trading
 * terminal's answer to that, and it earns its place for the same reason it
 * does on a real desk: peripheral awareness, read without looking directly
 * at it.
 *
 * Deliberately brief and low-contrast. A price that pulses continuously
 * stops meaning anything, and this platform is meant to read as an
 * instrument rather than a slot machine.
 */
export function PriceTicker({
  value,
  decimals,
  className,
}: {
  value: number;
  decimals: number;
  className?: string;
}) {
  const previous = useRef<number | null>(null);
  const [direction, setDirection] = useState<"up" | "down" | null>(null);

  useEffect(() => {
    const before = previous.current;
    previous.current = value;
    // First render is not a move. Flashing on mount would tell the reader
    // something happened when nothing did.
    if (before === null || before === value) return;
    setDirection(before < value ? "up" : "down");
    const id = window.setTimeout(() => setDirection(null), 700);
    return () => window.clearTimeout(id);
  }, [value]);

  return (
    <span
      className={cn(
        "font-mono-tabular tabular-nums transition-colors",
        direction === "up" && "tick-up",
        direction === "down" && "tick-down",
        className
      )}
    >
      {formatPrice(value, decimals)}
    </span>
  );
}
