import { TrendingUp } from "lucide-react";
import { cn } from "@/lib/utils";

export function Logo({ className }: { className?: string }) {
  return (
    <div className={cn("flex items-center gap-2.5 font-semibold tracking-tight", className)}>
      <span className="relative flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-primary/25 to-primary/5 text-primary ring-1 ring-inset ring-primary/25">
        <TrendingUp className="h-4.5 w-4.5" strokeWidth={2.25} />
      </span>
      <span className="text-[15px] leading-none text-foreground">
        NorthFX<span className="text-primary">Trade</span>
      </span>
    </div>
  );
}
