import Link from "next/link";
import { getModels } from "@/lib/admin";
import { ASSET_CONFIGS } from "@/data/assets";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ModelNotReady } from "@/components/admin/model-not-ready";
import { formatDateTimeUTC, formatPercent } from "@/lib/utils";
import { ArrowLeft } from "lucide-react";

export const dynamic = "force-dynamic";

export default async function AdminModelDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const result = await getModels();
  const model = result.ok ? result.models.find((m) => m.id === id) : undefined;

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <Link
        href="/admin/models"
        className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="h-4 w-4" /> Back to models
      </Link>

      {/* Deliberately NOT notFound(). Today every id is missing because no
          model has been trained, and a 404 would read as a broken link
          rather than as the true state of the pipeline. */}
      {!model ? (
        <ModelNotReady
          detail={
            result.ok
              ? `No model version with id ${id}. No models have been trained yet, so every id on this route is currently unknown.`
              : `Could not read the model tables: ${result.error}`
          }
        />
      ) : (
        <Card>
          <CardHeader className="flex-row items-center justify-between space-y-0">
            <div>
              <CardTitle>{model.name}</CardTitle>
              <p className="text-xs text-muted-foreground">
                {model.asset ? ASSET_CONFIGS[model.asset].displayName : "unknown pair"}
                {model.expiryMinutes !== null && ` · ${model.expiryMinutes}m expiry`} · {model.version}
              </p>
            </div>
            <Badge>{model.status}</Badge>
          </CardHeader>
          <CardContent className="space-y-6">
            <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
              <Field label="Model type" value={model.modelType} />
              <Field label="Trained at" value={model.trainedAt ? formatDateTimeUTC(model.trainedAt) : "—"} />
              <Field
                label="Training period"
                value={
                  model.trainingPeriodStart && model.trainingPeriodEnd
                    ? `${model.trainingPeriodStart} → ${model.trainingPeriodEnd}`
                    : "—"
                }
              />
              <Field
                label="Test accuracy"
                value={model.testAccuracy !== null ? formatPercent(model.testAccuracy) : "—"}
              />
              <Field
                label="A++ accuracy"
                value={model.aPlusPlusAccuracy !== null ? formatPercent(model.aPlusPlusAccuracy) : "—"}
              />
              <Field
                label="Signal coverage"
                value={model.signalCoverage !== null ? `${model.signalCoverage}%` : "—"}
              />
              <Field label="Activated" value={model.activatedAt ? formatDateTimeUTC(model.activatedAt) : "—"} />
              <Field label="Artifact" value={model.artifactUri ?? "—"} />
            </div>
            <div className="flex flex-wrap gap-2 border-t border-border pt-4">
              <Button variant="outline" disabled>Validate</Button>
              <Button disabled>Activate</Button>
              <Button variant="outline" disabled>Archive</Button>
            </div>
            <p className="text-xs text-muted-foreground">
              Controls are disabled until the training pipeline exists — a button that
              looks live but does nothing is worse than one that admits it. Activation
              is a deliberate manual action, never automatic on training completion.
            </p>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-[11px] uppercase tracking-wide text-muted-foreground">{label}</p>
      <p className="break-all text-sm font-medium text-foreground">{value}</p>
    </div>
  );
}
