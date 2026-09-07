import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import type { EngineHeartbeat } from "@/lib/engine-status";
import { Activity, AlertTriangle, PowerOff } from "lucide-react";

/**
 * States the engine's own liveness as a fact rather than an inference.
 *
 * Every card on this dashboard used to guess "engine may be stopped" from
 * a decision being old, which is wrong in both directions: an engine that
 * runs constantly and declines everything looks dead, and one that has
 * genuinely died looks merely selective. This reads the heartbeat the
 * engine writes each cycle, so silence is never ambiguous again.
 */
export function EngineHeartbeatBanner({ beats }: { beats: EngineHeartbeat[] }) {
  if (beats.length === 0) {
    return (
      <div className="flex items-start gap-2.5 rounded-lg border border-destructive/30 bg-destructive/5 px-3.5 py-2.5 text-xs leading-relaxed">
        <PowerOff className="mt-0.5 h-4 w-4 shrink-0 text-destructive" />
        <span className="text-muted-foreground">
          <strong className="font-semibold text-destructive">
            The engine has never reported in.
          </strong>{" "}
          No heartbeat has been recorded, so nothing on this page is live. Start
          the collector (<code className="font-mono-tabular">start-collector.bat</code>)
          and leave its window open.
        </span>
      </div>
    );
  }

  return (
    <div className="grid gap-2 sm:grid-cols-2">
      {beats.map((beat) => {
        // Two cycles' grace before calling it late — one slow fetch is not
        // an outage, and crying wolf teaches the reader to ignore this line.
        const interval = Number(beat.details.interval_seconds ?? 300);
        const late = beat.ageSeconds > interval * 2.5;
        const offline = beat.status === "Offline";
        const reason = typeof beat.details.reason === "string" ? beat.details.reason : null;

        return (
          <Card
            key={beat.component}
            className={cn(
              (late || offline) && "border-destructive/40"
            )}
          >
            <CardContent className="flex items-start gap-2.5 p-3.5">
              {offline ? (
                <PowerOff className="mt-0.5 h-4 w-4 shrink-0 text-destructive" />
              ) : late ? (
                <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-notrade" />
              ) : (
                <Activity className="mt-0.5 h-4 w-4 shrink-0 text-call" />
              )}
              <div className="min-w-0 space-y-0.5">
                <p className="text-xs font-semibold text-foreground">{beat.component}</p>
                <p className="text-xs text-muted-foreground">
                  {offline
                    ? "Not running"
                    : late
                      ? `Last ran ${formatAge(beat.ageSeconds)} ago — expected every ${Math.round(interval / 60)} min`
                      : `Ran ${formatAge(beat.ageSeconds)} ago`}
                </p>
                {reason && <p className="text-xs text-destructive">{reason}</p>}
              </div>
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}

function formatAge(seconds: number): string {
  if (seconds < 90) return `${seconds}s`;
  const minutes = Math.round(seconds / 60);
  if (minutes < 90) return `${minutes}m`;
  return `${Math.round(minutes / 60)}h`;
}
