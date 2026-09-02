import { getAdminUsers } from "@/lib/admin";
import { createClient } from "@/lib/supabase/server";
import { AccessControls } from "@/components/admin/access-controls";
import { Card, CardContent } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { formatDateTimeUTC } from "@/lib/utils";
import { AlertTriangle } from "lucide-react";

export const dynamic = "force-dynamic";

export default async function AdminUsersPage() {
  const result = await getAdminUsers();
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  const pendingCount = result.ok
    ? result.users.filter((u) => u.accessStatus === "PENDING").length
    : 0;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold tracking-tight text-foreground">Users</h1>
        <p className="text-sm text-muted-foreground">
          Real accounts from Supabase Auth and the profiles table. Signup does not grant
          access — an account sees nothing until it is approved here.
        </p>
      </div>

      {pendingCount > 0 && (
        <div className="rounded-lg border border-notrade/25 bg-notrade-muted/40 px-3.5 py-2 text-xs text-notrade-foreground/90">
          <strong className="font-semibold">
            {pendingCount} {pendingCount === 1 ? "account is" : "accounts are"} waiting for approval.
          </strong>{" "}
          They are listed first below and can see nothing until a decision is made.
        </div>
      )}

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
                    <TableHead>Access</TableHead>
                    <TableHead>Joined</TableHead>
                    <TableHead className="text-right">Actions</TableHead>
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
                      <TableCell>
                        <Badge
                          variant={
                            u.accessStatus === "APPROVED"
                              ? "call"
                              : u.accessStatus === "REJECTED"
                                ? "destructive"
                                : "outline"
                          }
                        >
                          {u.accessStatus ?? "unknown"}
                        </Badge>
                      </TableCell>
                      <TableCell className="whitespace-nowrap text-xs text-muted-foreground">
                        {formatDateTimeUTC(u.createdAt)}
                      </TableCell>
                      <TableCell className="text-right">
                        <AccessControls
                          userId={u.id}
                          status={u.accessStatus}
                          isSelf={u.id === user?.id}
                        />
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
          <p className="text-xs text-muted-foreground">
            Access decisions go through <code className="rounded bg-secondary px-1 py-0.5">admin_set_access()</code>,
            which refuses non-admins, refuses to act on your own account, and writes an audit log entry. Roles are
            still not editable here — promoting someone to admin is a privilege escalation path and needs a
            deliberate act, not an inline toggle. Plans stay read-only until a payment provider is integrated.
          </p>
        </>
      )}
    </div>
  );
}
