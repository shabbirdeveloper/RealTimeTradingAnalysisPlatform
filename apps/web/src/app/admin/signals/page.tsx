import { HISTORICAL_SIGNALS, REJECTED_OPPORTUNITIES } from "@/data/history";
import { ASSET_CONFIGS } from "@/data/assets";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Card, CardContent } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { DirectionBadge, GradeBadge, DemoDataBanner } from "@/components/shared/badges";
import { formatDateTimeUTC, formatPercent } from "@/lib/utils";

export default function AdminSignalsPage() {
  const accepted = HISTORICAL_SIGNALS.slice(0, 100);
  const rejected = REJECTED_OPPORTUNITIES;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold tracking-tight text-foreground">Signals</h1>
        <p className="text-sm text-muted-foreground">Both accepted signals and rejected opportunities are retained for analysis.</p>
      </div>
      <DemoDataBanner />

      <Tabs defaultValue="accepted">
        <TabsList>
          <TabsTrigger value="accepted">Accepted ({accepted.length})</TabsTrigger>
          <TabsTrigger value="rejected">Rejected ({rejected.length})</TabsTrigger>
        </TabsList>

        <TabsContent value="accepted">
          <Card>
            <CardContent className="p-0">
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
                      <TableCell>{s.expiryMinutes}m</TableCell>
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
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Time</TableHead>
                    <TableHead>Asset</TableHead>
                    <TableHead>Potential direction</TableHead>
                    <TableHead>Confidence</TableHead>
                    <TableHead>Reason</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {rejected.map((r) => (
                    <TableRow key={r.id}>
                      <TableCell className="whitespace-nowrap text-xs text-muted-foreground">{formatDateTimeUTC(r.generatedAt)}</TableCell>
                      <TableCell>{ASSET_CONFIGS[r.asset].displayName}</TableCell>
                      <TableCell><DirectionBadge direction={r.potentialDirection} /></TableCell>
                      <TableCell className="font-mono-tabular">{r.confidence !== null ? formatPercent(r.confidence) : "—"}</TableCell>
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
