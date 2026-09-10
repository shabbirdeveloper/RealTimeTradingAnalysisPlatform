"use client";
import { useState } from "react";
import { Sidebar } from "@/components/layout/sidebar";
import { Topbar } from "@/components/layout/topbar";
import { MobileBottomNav, MobileDrawer } from "@/components/layout/mobile-nav";
import { PageTransition } from "@/components/layout/page-transition";

/**
 * The visual shell only. Authentication moved OUT of here and into
 * layout.tsx, which is a server component -- a "use client" file cannot
 * verify a session, and this one never did.
 */
export function DashboardShell({ children }: { children: React.ReactNode }) {
  const [drawerOpen, setDrawerOpen] = useState(false);

  return (
    <div className="flex min-h-screen">
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <Topbar onMenuClick={() => setDrawerOpen(true)} />
        <main className="flex-1 px-4 pb-20 pt-5 lg:px-6 lg:pb-8"><PageTransition>{children}</PageTransition></main>
      </div>
      <MobileBottomNav />
      <MobileDrawer open={drawerOpen} onClose={() => setDrawerOpen(false)} />
    </div>
  );
}
