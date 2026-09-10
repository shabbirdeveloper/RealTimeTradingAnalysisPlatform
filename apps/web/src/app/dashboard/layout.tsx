import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";
import { DashboardShell } from "./dashboard-shell";

/**
 * The authoritative check for every /dashboard route.
 *
 * WHY IT LIVES HERE AND NOT ONLY IN MIDDLEWARE
 *
 * It used to live only in middleware. That put the single protection for
 * /dashboard inside the Edge runtime, where @supabase/ssr could not be
 * loaded -- and when the module failed, middleware failed with it and
 * returned 500 for the entire site. Three increasingly careful guards
 * inside the middleware function could not fix that, because the failure
 * was the module, not the code.
 *
 * A server component runs on the Node runtime, has no such constraint,
 * and sits closer to the data it is protecting. /admin already worked
 * this way; /dashboard did not, which is the only reason middleware had
 * to carry real verification at all.
 *
 * Middleware keeps a cheap cookie-presence check for the early redirect.
 * This is the check that decides.
 */
export default async function DashboardLayout({ children }: { children: React.ReactNode }) {
  let userId: string | null = null;
  let role: string | null = null;
  let accessStatus: string | null = null;

  try {
    const supabase = await createClient();
    const { data } = await supabase.auth.getUser();
    userId = data?.user?.id ?? null;

    if (userId) {
      const { data: profile } = await supabase
        .from("profiles")
        .select("role, access_status")
        .eq("id", userId)
        .maybeSingle();
      const row = profile as { role?: string; access_status?: string } | null;
      role = row?.role ?? null;
      accessStatus = row?.access_status ?? null;
    }
  } catch {
    // Cannot verify -> not verified. Deliberately not "assume signed in":
    // a database that is unreachable must not become an open door.
    redirect("/login?error=unavailable");
  }

  if (!userId) redirect("/login?redirectedFrom=/dashboard");

  // Admins are never held at the approval gate -- the console that approves
  // people has to stay reachable. Anything other than APPROVED for a
  // non-admin waits, INCLUDING a missing column on a database that has not
  // run migration 18 (undefined !== 'APPROVED'), which fails closed.
  if (role !== "admin" && accessStatus !== "APPROVED") {
    redirect("/pending");
  }

  return <DashboardShell>{children}</DashboardShell>;
}
