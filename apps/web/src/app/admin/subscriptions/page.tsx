import { Card, CardContent } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { DemoDataBanner } from "@/components/shared/badges";

const SUBSCRIPTIONS = [
  { user: "amelia@example.com", plan: "Pro", status: "Active", renews: "2026-09-02" },
  { user: "marcus@example.com", plan: "Pro", status: "Active", renews: "2026-09-19" },
  { user: "diego@example.com", plan: "Institutional", status: "Active", renews: "2026-09-30" },
  { user: "old.user@example.com", plan: "Pro", status: "Canceled", renews: "—" },
];

export default function AdminSubscriptionsPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold tracking-tight text-foreground">Subscriptions</h1>
        <p className="text-sm text-muted-foreground">Billing state per account.</p>
      </div>
      <DemoDataBanner />
      <Card>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>User</TableHead>
                <TableHead>Plan</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Renews</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {SUBSCRIPTIONS.map((s) => (
                <TableRow key={s.user}>
                  <TableCell className="text-muted-foreground">{s.user}</TableCell>
                  <TableCell>{s.plan}</TableCell>
                  <TableCell><Badge variant={s.status === "Active" ? "call" : "outline"}>{s.status}</Badge></TableCell>
                  <TableCell className="text-xs text-muted-foreground">{s.renews}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
