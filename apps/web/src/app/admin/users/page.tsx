import { getAdminUsers } from "@/lib/admin";
import { Card, CardContent } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { formatDateTimeUTC } from "@/lib/utils";
import { AlertTriangle } from "lucide-react";

export const dynamic = "force-dynamic";

export default async function AdminUsersPage() {
  const result = await getAdminUsers();

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold tracking-tight text-foreground">Users</h1>
        <p className="text-sm text-muted-foreground">Real accounts from Supabase Auth and the profiles table.</p>
      </div>

      {!result.ok ? (
        <div className="flex items-start gap-2.5 rounded-lg border border-put/30 bg-put-muted/40 px-3.5 py-2.5 text-xs text-put-foreground">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          <span>
            <strong className="font-semibold">Could not load users.</strong> {result.error} This page reads through the{" "}
            <code className="rounded bg-secondary px-1 py-0.5">admin_list_users()</code> function — check that
            migration <code className="rounded bg-secondary px-1 py-0.5">20260830000013</code> has been run and that
            your account has the admin role.
          </span>
        </div>
      ) : result.users.length === 0 ? (
        <Card>
          <CardContent className="p-5 text-sm text-muted-foreground">No accounts yet.</CardContent>
        </Card>
      ) : (
        <>
          <Card>
            <CardContent className="p-0">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Name</TableHead>
                    <TableHead>Email</TableHead>
                    <TableHead>Plan</TableHead>
                    <TableHead>Role</TableHead>
                    <TableHead>Joined</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {result.users.map((u) => (
                    <TableRow key={u.id}>
                      <TableCell className="font-medium text-foreground">{u.displayName ?? "—"}</TableCell>
                      <TableCell className="text-muted-foreground">{u.email ?? "—"}</TableCell>
                      <TableCell>
                        <Badge variant="outline">{u.plan}</Badge>
                        {u.subscriptionStatus && u.subscriptionStatus !== "active" && (
                          <span className="ml-2 text-xs text-muted-foreground">{u.subscriptionStatus}</span>
                        )}
                      </TableCell>
                      <TableCell>
                        <Badge variant={u.role === "admin" ? "call" : "secondary"}>{u.role}</Badge>
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
          <p className="text-xs text-muted-foreground">
            Read-only. Changing a role or plan from here isn&apos;t implemented — a role change is a privilege
            escalation path, so it needs a deliberate, audited action rather than an inline toggle. Plans stay
            read-only until a payment provider is integrated.
          </p>
        </>
      )}
    </div>
  );
}
