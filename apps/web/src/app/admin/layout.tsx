/**
 * Admin shell, with its own server-side role check.
 *
 * The middleware already gates /admin (spec section 38), and this is a
 * second, independent check on purpose. Middleware runs on the edge and
 * its matcher is a configuration file one careless edit away from not
 * covering a route; this one runs inside the request that actually
 * renders the page, so a route can never be admin-only "by matcher" and
 * public in fact. Both fail closed: an unreachable profiles table means
 * nobody is an admin, not everybody.
 */
import { redirect } from "next/navigation";
import { AdminSidebar } from "@/components/layout/admin-sidebar";
import { PageTransition } from "@/components/layout/page-transition";
import { createClient } from "@/lib/supabase/server";

export default async function AdminLayout({ children }: { children: React.ReactNode }) {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (!user) redirect("/login?redirectedFrom=/admin");

  let role: string | null = null;
  try {
    const { data: profile } = await supabase
      .from("profiles")
      .select("role")
      .eq("id", user.id)
      .maybeSingle();
    role = (profile as { role?: string } | null)?.role ?? null;
  } catch {
    role = null;
  }
  if (role !== "admin") redirect("/dashboard");

  return (
    <div className="flex min-h-screen">
      <AdminSidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex h-14 items-center border-b border-border bg-background/85 px-6 backdrop-blur">
          <p className="text-sm font-medium text-foreground">Admin Console</p>
          <span className="ml-3 text-xs text-muted-foreground">
            Role-gated · figures read from the database
          </span>
        </header>
        <main className="flex-1 px-6 py-6">
          <PageTransition>{children}</PageTransition>
        </main>
      </div>
    </div>
  );
}
