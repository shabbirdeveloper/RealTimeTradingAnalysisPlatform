import { notFound } from "next/navigation";
import Link from "next/link";
import { MODELS } from "@/data/history";
import { ASSET_CONFIGS } from "@/data/assets";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { DemoDataBanner } from "@/components/shared/badges";
import { formatDateTimeUTC, formatPercent } from "@/lib/utils";
import { ArrowLeft } from "lucide-react";

export function generateStaticParams() {
  return MODELS.map((m) => ({ id: m.id }));
}

export default async function AdminModelDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const model = MODELS.find((m) => m.id === id);
  if (!model) notFound();
  const cfg = ASSET_CONFIGS[model.asset];

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <Link href="/admin/models" className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeft className="h-4 w-4" /> Back to models
      </Link>
      <DemoDataBanner />
      <Card>
        <CardHeader className="flex-row items-center justify-between space-y-0">
          <div>
            <CardTitle>{model.name}</CardTitle>
            <p className="text-xs text-muted-foreground">{cfg.displayName} · {model.expiryMinutes}m expiry · {model.version}</p>
          </div>
          <Badge>{model.status}</Badge>
        </CardHeader>
        <CardContent className="space-y-6">
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
            <Field label="Training date" value={formatDateTimeUTC(model.trainingDate)} />
            <Field label="Training period" value={model.trainingPeriod} />
            <Field label="Test accuracy" value={model.testAccuracy !== null ? formatPercent(model.testAccuracy) : "—"} />
            <Field label="A++ accuracy" value={model.aPlusPlusAccuracy !== null ? formatPercent(model.aPlusPlusAccuracy) : "—"} />
            <Field label="Signal coverage" value={model.signalCoverage !== null ? `${model.signalCoverage}%` : "—"} />
            <Field label="Status" value={model.status} />
          </div>
          <div className="flex flex-wrap gap-2 border-t border-border pt-4">
            <Button variant="outline" disabled>Validate</Button>
            <Button disabled>Activate</Button>
            <Button variant="outline" disabled>Archive</Button>
          </div>
          <p className="text-xs text-muted-foreground">
            Activation is a deliberate manual action, never automatic on training completion, per platform policy.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-[11px] uppercase tracking-wide text-muted-foreground">{label}</p>
      <p className="text-sm font-medium text-foreground">{value}</p>
    </div>
  );
}
