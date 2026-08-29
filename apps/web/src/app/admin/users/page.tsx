import { Card, CardContent } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { DemoDataBanner } from "@/components/shared/badges";

const USERS = [
  { name: "Shabbir Developer", email: "shabbirabroud@gmail.com", plan: "Free", role: "Admin", joined: "2026-03-14" },
  { name: "Amelia Chen", email: "amelia@example.com", plan: "Pro", role: "User", joined: "2026-05-02" },
  { name: "Marcus Webb", email: "marcus@example.com", plan: "Pro", role: "User", joined: "2026-06-19" },
  { name: "Priya Nair", email: "priya@example.com", plan: "Free", role: "User", joined: "2026-07-08" },
  { name: "Diego Alves", email: "diego@example.com", plan: "Institutional", role: "User", joined: "2026-07-30" },
];

export default function AdminUsersPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold tracking-tight text-foreground">Users</h1>
        <p className="text-sm text-muted-foreground">Account, role and plan management.</p>
      </div>
      <DemoDataBanner />
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
              {USERS.map((u) => (
                <TableRow key={u.email}>
                  <TableCell className="font-medium text-foreground">{u.name}</TableCell>
                  <TableCell className="text-muted-foreground">{u.email}</TableCell>
                  <TableCell><Badge variant="secondary">{u.plan}</Badge></TableCell>
                  <TableCell>{u.role}</TableCell>
                  <TableCell className="text-xs text-muted-foreground">{u.joined}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
