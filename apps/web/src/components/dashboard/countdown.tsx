"use client";
import { useNow } from "@/lib/use-now";
import { formatCountdown } from "@/lib/utils";
import { Clock } from "lucide-react";

export function CountdownBadge({ validUntil }: { validUntil: string }) {
  const now = useNow(1000);
  if (!now) return <span className="font-mono-tabular text-sm text-muted-foreground">--:--</span>;
  const ms = new Date(validUntil).getTime() - now.getTime();
  const expired = ms <= 0;
  return (
    <span className={`flex items-center gap-1 font-mono-tabular text-sm font-semibold ${expired ? "text-muted-foreground" : "text-primary"}`}>
      <Clock className="h-3.5 w-3.5" />
      {expired ? "Expired" : formatCountdown(ms)}
    </span>
  );
}
