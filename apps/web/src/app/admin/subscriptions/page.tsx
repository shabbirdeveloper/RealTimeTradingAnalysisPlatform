import { getAdminUsers } from "@/lib/admin";
import { Card, CardContent } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { formatDateTimeUTC } from "@/lib/utils";

export const dynamic = "force-dynamic";

export default async function AdminSubscriptionsPage() {
  const result = await getAdminUsers();

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold tracking-tight text-foreground">Subscriptions</h1>
        <p className="text-sm text-muted-foreground">
          Billing state per account, from the <code className="font-mono-tabular text-xs">subscriptions</code> table.
          No payment provider is connected yet (Phase 10), so every row here was
          created by signup, not by a charge.
        </p>
      </div>

      {!result.ok ? (
        <EmptyState>Could not load accounts: {result.error}</EmptyState>
      ) : result.users.length === 0 ? (
        <EmptyState>No accounts have registered yet.</EmptyState>
      ) : (
        <Card>
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>User</TableHead>
                  <TableHead>Plan</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Registered</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {result.users.map((u) => (
                  <TableRow key={u.id}>
                    <TableCell className="font-medium text-foreground">
                      {u.email ?? u.displayName ?? u.id}
                    </TableCell>
                    <TableCell className="capitalize">{u.plan}</TableCell>
                    <TableCell>
                      <Badge variant={u.subscriptionStatus === "active" ? "default" : "outline"}>
                        {u.subscriptionStatus ?? "none"}
                      </Badge>
                    </TableCell>
                    <TableCell className="whitespace-nowrap text-xs text-muted-foreground">
                      {formatDateTimeUTC(u.createdAt)}
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

function EmptyState({ children }: { children: React.ReactNode }) {
  return (
    <Card className="border-dashed">
      <CardContent className="p-6">
        <p className="text-sm text-muted-foreground">{children}</p>
      </CardContent>
    </Card>
  );
}
