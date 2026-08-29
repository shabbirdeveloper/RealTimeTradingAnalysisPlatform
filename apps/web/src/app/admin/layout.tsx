// NOTE: This is the Phase-1 frontend shell only. Real admin protection must
// enforce role checks server-side (Supabase Auth + RLS + middleware) before
// any of these routes ship — see project spec sections 28 and 38. Nothing
// here should be treated as an access control mechanism yet.
import { AdminSidebar } from "@/components/layout/admin-sidebar";
import { PageTransition } from "@/components/layout/page-transition";

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen">
      <AdminSidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex h-14 items-center border-b border-border bg-background/85 px-6 backdrop-blur">
          <p className="text-sm font-medium text-foreground">Admin Console</p>
          <span className="ml-3 text-xs text-muted-foreground">Role-gated in production — demo data only</span>
        </header>
        <main className="flex-1 px-6 py-6"><PageTransition>{children}</PageTransition></main>
      </div>
    </div>
  );
}
