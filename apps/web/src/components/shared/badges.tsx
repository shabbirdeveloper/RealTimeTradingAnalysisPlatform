import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import type { DataStatus, Direction, MarketRegime, SignalGrade } from "@/types";
import { ArrowUpRight, ArrowDownRight, MinusCircle, Radio, Clock, AlertTriangle, WifiOff, Sparkles } from "lucide-react";

export function DirectionBadge({ direction, className }: { direction: Direction; className?: string }) {
  if (direction === "CALL") {
    return (
      <Badge variant="call" className={cn("gap-1 font-semibold tracking-wide", className)}>
        <ArrowUpRight className="h-3 w-3" strokeWidth={2.75} /> CALL
      </Badge>
    );
  }
  if (direction === "PUT") {
    return (
      <Badge variant="put" className={cn("gap-1 font-semibold tracking-wide", className)}>
        <ArrowDownRight className="h-3 w-3" strokeWidth={2.75} /> PUT
      </Badge>
    );
  }
  return (
    <Badge variant="notrade" className={cn("gap-1 font-semibold tracking-wide", className)}>
      <MinusCircle className="h-3 w-3" /> NO TRADE
    </Badge>
  );
}

export function GradeBadge({ grade, className }: { grade: SignalGrade; className?: string }) {
  if (grade === "A++") {
    return (
      <span
        className={cn(
          "inline-flex items-center gap-1 rounded-md border border-aplusplus/40 bg-gradient-to-b from-aplusplus/25 to-aplusplus/10 px-2 py-0.5 text-xs font-bold tracking-wide text-aplusplus shadow-[0_1px_0_0_hsl(var(--aplusplus)/0.2)_inset]",
          className
        )}
      >
        <Sparkles className="h-3 w-3" /> A++
      </span>
    );
  }
  if (grade === "REJECTED") return <Badge variant="outline" className={cn("text-muted-foreground", className)}>REJECTED</Badge>;
  return <Badge variant="secondary" className={cn("font-semibold", className)}>{grade}</Badge>;
}

const REGIME_LABEL: Record<MarketRegime, string> = {
  TRENDING_UP: "Trending Up",
  TRENDING_DOWN: "Trending Down",
  RANGING: "Ranging",
  HIGH_VOLATILITY: "High Volatility",
  LOW_VOLATILITY: "Low Volatility",
  NEWS_MODE: "News Mode",
  UNSTABLE: "Unstable",
};

export function RegimeBadge({ regime, className }: { regime: MarketRegime; className?: string }) {
  const tone =
    regime === "TRENDING_UP" || regime === "TRENDING_DOWN"
      ? "border-primary/30 bg-primary/10 text-primary"
      : regime === "NEWS_MODE" || regime === "UNSTABLE"
      ? "border-put/30 bg-put-muted text-put-foreground"
      : regime === "HIGH_VOLATILITY"
      ? "border-notrade/30 bg-notrade-muted text-notrade-foreground"
      : "border-border text-muted-foreground";
  return <Badge variant="outline" className={cn("font-medium", tone, className)}>{REGIME_LABEL[regime]}</Badge>;
}

export function DataStatusPill({ status, className }: { status: DataStatus; className?: string }) {
  const map: Record<DataStatus, { label: string; cls: string; icon: React.ReactNode }> = {
    LIVE: { label: "LIVE", cls: "text-call border-call/30 bg-call-muted", icon: <Radio className="h-3 w-3 animate-pulse-slow" /> },
    DELAYED: { label: "DELAYED", cls: "text-notrade border-notrade/30 bg-notrade-muted", icon: <Clock className="h-3 w-3" /> },
    STALE: { label: "STALE", cls: "text-put border-put/30 bg-put-muted", icon: <AlertTriangle className="h-3 w-3" /> },
    OFFLINE: { label: "OFFLINE", cls: "text-muted-foreground border-border", icon: <WifiOff className="h-3 w-3" /> },
  };
  const m = map[status];
  return (
    <span className={cn("inline-flex items-center gap-1.5 rounded-md border px-2 py-0.5 text-[11px] font-bold tracking-wider", m.cls, className)}>
      {m.icon}
      {m.label}
    </span>
  );
}

export function DemoDataBanner({ className }: { className?: string }) {
  return (
    <div className={cn("flex items-center gap-2.5 rounded-lg border border-notrade/20 bg-notrade-muted/40 px-3.5 py-2 text-xs text-notrade-foreground/90", className)}>
      <AlertTriangle className="h-3.5 w-3.5 shrink-0 text-notrade" />
      <span>
        <strong className="font-semibold">DEMO DATA.</strong> All prices, signals, confidence values and results on this
        screen are synthetic placeholders for interface development — not live market analysis or real performance.
      </span>
    </div>
  );
}
