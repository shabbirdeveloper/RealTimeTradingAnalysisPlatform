import { Card, CardContent } from "@/components/ui/card";
import { AlertTriangle } from "lucide-react";

/**
 * What an admin sees when no model has been trained.
 *
 * The spec is explicit that the answer here is MODEL_NOT_READY rather
 * than a generated confidence, and this page is where that rule matters
 * most: a fabricated "91.2% A++ accuracy" sitting in an admin table is
 * precisely the figure someone would later quote as evidence the platform
 * works. An empty state cannot be misquoted.
 */
export function ModelNotReady({ detail }: { detail?: string }) {
  return (
    <Card className="border-dashed">
      <CardContent className="space-y-3 p-6">
        <div className="flex items-center gap-2">
          <AlertTriangle className="h-4 w-4 text-notrade" />
          <span className="font-mono-tabular text-sm font-semibold text-notrade">MODEL_NOT_READY</span>
        </div>
        <p className="max-w-2xl text-sm leading-relaxed text-muted-foreground">
          No trained model exists. The ML pipeline (Phase 6) has not been built, so
          the <code className="font-mono-tabular text-xs">models</code> and{" "}
          <code className="font-mono-tabular text-xs">model_versions</code> tables are
          empty — which is the honest state, not a failure.
        </p>
        <p className="max-w-2xl text-sm leading-relaxed text-muted-foreground">
          Until then every signal is scored on technical rules alone, grades are
          capped at B, and <code className="font-mono-tabular text-xs">calibrated_confidence</code> stays
          null rather than carrying a number nothing produced. This page will fill
          in when real training runs write real results.
        </p>
        {detail && (
          <p className="rounded-md border border-border bg-secondary/40 p-3 text-xs text-muted-foreground">
            {detail}
          </p>
        )}
      </CardContent>
    </Card>
  );
}
