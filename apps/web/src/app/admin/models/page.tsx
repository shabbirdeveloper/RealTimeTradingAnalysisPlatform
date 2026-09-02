import Link from "next/link";
import { getModels } from "@/lib/admin";
import { ASSET_CONFIGS } from "@/data/assets";
import { Card, CardContent } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { ModelNotReady } from "@/components/admin/model-not-ready";
import { formatDateTimeUTC, formatPercent } from "@/lib/utils";

export const dynamic = "force-dynamic";

const STATUS_VARIANT: Record<string, "default" | "secondary" | "outline" | "destructive"> = {
  ACTIVE: "default", READY: "secondary", VALIDATING: "outline",
  TRAINING: "outline", ARCHIVED: "outline", FAILED: "destructive",
};

export default async function AdminModelsPage() {
  const result = await getModels();

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold tracking-tight text-foreground">Models</h1>
        <p className="text-sm text-muted-foreground">
          One model per asset/expiry combination. Nothing is auto-deployed on training
          completion — promotion to ACTIVE is always a deliberate act.
        </p>
      </div>

      {!result.ok ? (
        <ModelNotReady detail={`Could not read the model tables: ${result.error}`} />
      ) : result.models.length === 0 ? (
        <ModelNotReady />
      ) : (
        <Card>
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Model</TableHead>
                  <TableHead>Pair</TableHead>
                  <TableHead>Expiry</TableHead>
                  <TableHead>Version</TableHead>
                  <TableHead>Trained</TableHead>
                  <TableHead>Test accuracy</TableHead>
                  <TableHead>A++ accuracy</TableHead>
                  <TableHead>Coverage</TableHead>
                  <TableHead>Status</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {result.models.map((m) => (
                  <TableRow key={m.id}>
                    <TableCell>
                      <Link
                        href={`/admin/models/${m.id}`}
                        className="font-medium text-foreground hover:text-primary hover:underline"
                      >
                        {m.name}
                      </Link>
                    </TableCell>
                    <TableCell>{m.asset ? ASSET_CONFIGS[m.asset].displayName : "—"}</TableCell>
                    <TableCell>{m.expiryMinutes !== null ? `${m.expiryMinutes}m` : "—"}</TableCell>
                    <TableCell className="font-mono-tabular text-xs">{m.version}</TableCell>
                    <TableCell className="whitespace-nowrap text-xs text-muted-foreground">
                      {m.trainedAt ? formatDateTimeUTC(m.trainedAt) : "—"}
                    </TableCell>
                    <TableCell className="font-mono-tabular">
                      {m.testAccuracy !== null ? formatPercent(m.testAccuracy) : "—"}
                    </TableCell>
                    <TableCell className="font-mono-tabular">
                      {m.aPlusPlusAccuracy !== null ? formatPercent(m.aPlusPlusAccuracy) : "—"}
                    </TableCell>
                    <TableCell className="font-mono-tabular">
                      {m.signalCoverage !== null ? `${m.signalCoverage}%` : "—"}
                    </TableCell>
                    <TableCell>
                      <Badge variant={STATUS_VARIANT[m.status] ?? "outline"}>{m.status}</Badge>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
