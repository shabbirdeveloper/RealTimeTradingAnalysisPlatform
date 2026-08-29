"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import { Logo } from "./logo";
import { ADMIN_NAV, BACK_TO_APP } from "./admin-nav-items";
import { ShieldAlert } from "lucide-react";

export function AdminSidebar() {
  const pathname = usePathname();
  return (
    <aside className="hidden w-64 shrink-0 flex-col border-r border-border/70 bg-card/30 lg:flex">
      <div className="flex h-14 items-center gap-2 border-b border-border/70 px-5">
        <Link href="/admin"><Logo /></Link>
        <span className="ml-auto flex items-center gap-1 rounded-md border border-put/30 bg-put-muted px-1.5 py-0.5 text-[10px] font-semibold text-put-foreground">
          <ShieldAlert className="h-3 w-3" /> ADMIN
        </span>
      </div>
      <nav className="flex-1 space-y-0.5 overflow-y-auto px-3 py-4">
        {ADMIN_NAV.map((item) => {
          const active = item.href === "/admin" ? pathname === "/admin" : pathname.startsWith(item.href);
          const Icon = item.icon;
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "group relative flex items-center gap-2.5 rounded-md px-3 py-2 text-sm font-medium transition-colors duration-200",
                active ? "bg-secondary/80 text-foreground" : "text-muted-foreground hover:bg-secondary/50 hover:text-foreground"
              )}
            >
              <span
                className={cn(
                  "absolute -left-3 top-1/2 h-4 w-0.5 -translate-y-1/2 rounded-full bg-put transition-all duration-200 ease-out",
                  active ? "scale-y-100 opacity-100" : "scale-y-0 opacity-0"
                )}
              />
              <Icon className={cn("h-4 w-4 shrink-0 transition-colors", active ? "text-put" : "text-muted-foreground/80 group-hover:text-foreground")} />
              {item.label}
            </Link>
          );
        })}
      </nav>
      <div className="border-t border-border p-3">
        <Link href={BACK_TO_APP.href} className="flex items-center gap-2.5 rounded-md px-3 py-2 text-sm font-medium text-muted-foreground hover:bg-secondary/60 hover:text-foreground">
          <BACK_TO_APP.icon className="h-4 w-4" />
          {BACK_TO_APP.label}
        </Link>
      </div>
    </aside>
  );
}
