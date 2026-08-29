import { cn } from "@/lib/utils";

/**
 * A small pulsing dot with an expanding ring, used to mark genuinely live
 * status (market feed, data status). Purely decorative — callers still
 * decide the actual status text/color; this just adds the motion.
 */
export function LiveDot({ className }: { className?: string }) {
  return (
    <span className={cn("relative inline-flex h-2 w-2 shrink-0", className)}>
      <span className="live-dot-ring" />
      <span className="relative inline-flex h-2 w-2 rounded-full bg-current" />
    </span>
  );
}
