"use client";
import { cn } from "@/lib/utils";

/**
 * CALL against PUT on one diverging axis.
 *
 * Two parallel bars made the reader subtract one from the other to see the
 * thing that actually decides the trade — how far apart the sides are. Here
 * both grow outward from a shared centre, so the gap is the shape you read
 * first, and a market that merely leans looks visibly different from one
 * that commits.
 *
 * The bars are also deliberately not normalised to fill the track. Empty
 * space on both sides means the evidence was absent rather than balanced,
 * and that distinction is the whole reason the two scores are kept
 * independent.
 */
export function SideMeter({
  call,
  put,
  className,
}: {
  call: number;
  put: number;
  className?: string;
}) {
  const difference = Math.abs(call - put);
  const leader = call === put ? null : call > put ? "call" : "put";

  return (
    <div className={cn("space-y-1.5", className)}>
      <div className="flex items-center justify-between text-[10px] font-medium uppercase tracking-[0.12em]">
        <span className={cn(leader === "put" ? "text-put" : "text-muted-foreground")}>Put {put}</span>
        <span className="text-muted-foreground">
          {difference} apart
        </span>
        <span className={cn(leader === "call" ? "text-call" : "text-muted-foreground")}>{call} Call</span>
      </div>

      <div className="relative h-2 w-full overflow-hidden rounded-full bg-secondary/70">
        {/* Centre line: the axis both sides are measured from. */}
        <div className="absolute inset-y-0 left-1/2 z-10 w-px -translate-x-1/2 bg-border" />

        <div className="absolute inset-y-0 right-1/2 w-1/2">
          <div
            className="meter-fill h-full rounded-l-full bg-put/85"
            style={{ width: `${Math.min(100, put)}%`, marginLeft: "auto", ["--meter-origin" as string]: "right" }}
          />
        </div>

        <div className="absolute inset-y-0 left-1/2 w-1/2">
          <div
            className="meter-fill h-full rounded-r-full bg-call/85"
            style={{ width: `${Math.min(100, call)}%`, ["--meter-origin" as string]: "left" }}
          />
        </div>
      </div>
    </div>
  );
}
