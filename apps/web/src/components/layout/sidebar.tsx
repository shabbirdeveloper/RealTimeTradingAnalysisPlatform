"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import { Logo } from "./logo";
import { DASHBOARD_NAV, MARKET_LINKS } from "./nav-items";
import { Shield } from "lucide-react";

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="hidden w-64 shrink-0 flex-col border-r border-border/70 bg-card/30 lg:flex">
      <div className="flex h-14 items-center border-b border-border/70 px-5">
        <Link href="/dashboard">
          <Logo />
        </Link>
      </div>
      <nav className="flex-1 space-y-0.5 overflow-y-auto px-3 py-4">
        {DASHBOARD_NAV.map((item) => {
          const isMarkets = item.href.startsWith("/dashboard/markets");
          const active = isMarkets
            ? pathname.startsWith("/dashboard/markets")
            : item.href === "/dashboard"
            ? pathname === "/dashboard"
            : pathname.startsWith(item.href);
          const Icon = item.icon;
          return (
            <div key={item.href}>
              <Link
                href={item.href}
                className={cn(
                  "group relative flex items-center gap-2.5 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                  active ? "bg-secondary/80 text-foreground" : "text-muted-foreground hover:bg-secondary/50 hover:text-foreground"
                )}
              >
                {active && <span className="absolute -left-3 top-1/2 h-4 w-0.5 -translate-y-1/2 rounded-full bg-primary" />}
                <Icon className={cn("h-4 w-4 shrink-0 transition-colors", active ? "text-primary" : "text-muted-foreground/80 group-hover:text-foreground")} />
                {item.label}
              </Link>
              {isMarkets && active && (
                <div className="ml-[1.65rem] mt-0.5 space-y-0.5 border-l border-border pl-3">
                  {MARKET_LINKS.map((m) => (
                    <Link
                      key={m.href}
                      href={m.href}
                      className={cn(
                        "block rounded-md px-2.5 py-1.5 text-xs font-medium transition-colors",
                        pathname === m.href ? "text-primary" : "text-muted-foreground hover:text-foreground"
                      )}
                    >
                      {m.label}
                    </Link>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </nav>
      <div className="border-t border-border p-3">
        <Link
          href="/admin"
          className="flex items-center gap-2.5 rounded-md px-3 py-2 text-sm font-medium text-muted-foreground transition-colors hover:bg-secondary/60 hover:text-foreground"
        >
          <Shield className="h-4 w-4" />
          Admin Console
        </Link>
      </div>
    </aside>
  );
}
