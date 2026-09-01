import { getAcceptedSignals, getRejectedOpportunities, getThresholdCurve } from "@/lib/admin";
import { ThresholdCurve } from "@/components/admin/threshold-curve";
import { ASSET_CONFIGS } from "@/data/assets";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Card, CardContent } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { DirectionBadge, GradeBadge } from "@/components/shared/badges";
import { expirySecondsOf, formatDateTimeUTC, formatExpiry, formatPercent } from "@/lib/utils";

export const dynamic = "force-dynamic";

export default async function AdminSignalsPage() {
  const [accepted, rejected, curve] = await Promise.all([
    getAcceptedSignals(), getRejectedOpportunities(), getThresholdCurve(),
  ]);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold tracking-tight text-foreground">Signals</h1>
        <p className="text-sm text-muted-foreground">Real accepted signals and real rejected opportunities, both retained for analysis.</p>
      </div>

      <ThresholdCurve report={curve} />

      <Tabs defaultValue="accepted">
        <TabsList>
          <TabsTrigger value="accepted">Accepted ({accepted.length})</TabsTrigger>
          <TabsTrigger value="rejected">Rejected ({rejected.length})</TabsTrigger>
        </TabsList>

        <TabsContent value="accepted">
          <Card>
            <CardContent className="p-0">
              {accepted.length === 0 && (
                <p className="p-4 text-sm text-muted-foreground">No signals generated yet — real, just empty right now.</p>
              )}
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Time</TableHead>
                    <TableHead>Asset</TableHead>
                    <TableHead>Direction</TableHead>
                    <TableHead>Confidence</TableHead>
                    <TableHead>Grade</TableHead>
                    <TableHead>Expiry</TableHead>
                    <TableHead>Result</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {accepted.map((s) => (
                    <TableRow key={s.id}>
                      <TableCell className="whitespace-nowrap text-xs text-muted-foreground">{formatDateTimeUTC(s.generatedAt)}</TableCell>
                      <TableCell>{ASSET_CONFIGS[s.asset].displayName}</TableCell>
                      <TableCell><DirectionBadge direction={s.direction} /></TableCell>
                      <TableCell className="font-mono-tabular">{s.confidence !== null ? formatPercent(s.confidence) : "—"}</TableCell>
                      <TableCell><GradeBadge grade={s.grade} /></TableCell>
                      <TableCell>{formatExpiry(expirySecondsOf(s))}</TableCell>
                      <TableCell className={s.result === "WON" ? "text-call" : s.result === "LOST" ? "text-put" : "text-muted-foreground"}>{s.result}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="rejected">
          <Card>
            <CardContent className="p-0">
              {rejected.length === 0 && (
                <p className="p-4 text-sm text-muted-foreground">No rejected opportunities yet — real, just empty right now.</p>
              )}
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Time</TableHead>
                    <TableHead>Asset</TableHead>
                    <TableHead>Potential direction</TableHead>
                    <TableHead>Technical score</TableHead>
                    <TableHead>Reason</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {rejected.map((r) => (
                    <TableRow key={r.id}>
                      <TableCell className="whitespace-nowrap text-xs text-muted-foreground">{formatDateTimeUTC(r.generatedAt)}</TableCell>
                      <TableCell>{ASSET_CONFIGS[r.asset].displayName}</TableCell>
                      <TableCell><DirectionBadge direction={r.potentialDirection} /></TableCell>
                      <TableCell className="font-mono-tabular">{r.technicalScore}/100</TableCell>
                      <TableCell className="text-sm text-muted-foreground">{r.reason}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
