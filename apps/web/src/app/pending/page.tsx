import Link from "next/link";
import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";
import { Card, CardContent } from "@/components/ui/card";
import { formatDateTimeUTC } from "@/lib/utils";
import { Clock, ShieldCheck, ShieldX } from "lucide-react";

export const dynamic = "force-dynamic";

/**
 * Where an unapproved account lands.
 *
 * The page is deliberately specific about which of the three states the
 * account is in. "Access denied" for someone who is simply waiting reads
 * as rejection, and they either give up or start mailing support about a
 * problem that does not exist.
 */
export default async function PendingPage() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) redirect("/login?redirectedFrom=/pending");

  const { data } = await supabase
    .from("profiles")
    .select("role, access_status, access_decided_at, access_note, created_at")
    .eq("id", user.id)
    .maybeSingle();

  const profile = data as {
    role?: string;
    access_status?: string;
    access_decided_at?: string | null;
    access_note?: string | null;
    created_at?: string;
  } | null;

  // Approved (or an admin) has no business here.
  if (profile?.role === "admin" || profile?.access_status === "APPROVED") {
    redirect("/dashboard");
  }

  const rejected = profile?.access_status === "REJECTED";

  return (
    <main className="flex min-h-screen items-center justify-center px-4 py-16">
      <Card className="w-full max-w-lg">
        <CardContent className="space-y-5 p-8">
          <span
            className={`flex h-11 w-11 items-center justify-center rounded-lg ring-1 ring-inset ${
              rejected
                ? "bg-put-muted text-put ring-put/25"
                : "bg-notrade-muted text-notrade ring-notrade/25"
            }`}
          >
            {rejected ? <ShieldX className="h-5 w-5" /> : <Clock className="h-5 w-5" />}
          </span>

          <div className="space-y-2">
            <h1 className="text-xl font-semibold tracking-tight text-foreground">
              {rejected ? "Access not granted" : "Waiting for approval"}
            </h1>
            <p className="text-sm leading-relaxed text-muted-foreground">
              {rejected
                ? "An administrator reviewed this account and did not grant access. If you think that was a mistake, reply to whoever invited you."
                : "Your account was created. Access to the platform is granted manually, so an administrator needs to approve it before signals become visible. You will not need to sign up again — just sign in later."}
            </p>
          </div>

          {profile?.access_note && (
            <p className="rounded-md border border-border bg-secondary/40 p-3 text-sm text-muted-foreground">
              {profile.access_note}
            </p>
          )}

          <dl className="space-y-1.5 border-t border-border pt-4 text-xs text-muted-foreground">
            <Row label="Signed in as" value={user.email ?? user.id} />
            {profile?.created_at && (
              <Row label="Registered" value={formatDateTimeUTC(profile.created_at)} />
            )}
            {profile?.access_decided_at && (
              <Row label="Reviewed" value={formatDateTimeUTC(profile.access_decided_at)} />
            )}
          </dl>

          {!rejected && (
            <p className="flex items-start gap-2 rounded-md border border-dashed border-border p-3 text-xs text-muted-foreground">
              <ShieldCheck className="mt-0.5 h-3.5 w-3.5 shrink-0" />
              <span>
                This page refreshes your status each time you open it. Nothing else is
                needed from you.
              </span>
            </p>
          )}

          <Link href="/" className="inline-block text-sm text-primary hover:underline">
            Back to the site
          </Link>
        </CardContent>
      </Card>
    </main>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-4">
      <dt>{label}</dt>
      <dd className="truncate font-mono-tabular text-foreground">{value}</dd>
    </div>
  );
}
