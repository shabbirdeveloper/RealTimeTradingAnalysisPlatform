"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import { MOBILE_NAV } from "./nav-items";

export function MobileBottomNav() {
  const pathname = usePathname();
  return (
    <nav className="fixed inset-x-0 bottom-0 z-30 flex h-16 items-stretch border-t border-border bg-card/95 backdrop-blur lg:hidden">
      {MOBILE_NAV.map((item) => {
        const active = item.href === "/dashboard" ? pathname === "/dashboard" : pathname.startsWith(item.href);
        const Icon = item.icon;
        return (
          <Link
            key={item.href}
            href={item.href}
            className={cn(
              "flex flex-1 flex-col items-center justify-center gap-0.5 text-[10px] font-medium",
              active ? "text-primary" : "text-muted-foreground"
            )}
          >
            <Icon className="h-5 w-5" />
            {item.label}
          </Link>
        );
      })}
    </nav>
  );
}

export function MobileDrawer({ open, onClose }: { open: boolean; onClose: () => void }) {
  const pathname = usePathname();
  if (!open) return null;
  const ALL = [
    ...MOBILE_NAV,
    { label: "Analyzer", href: "/dashboard/analyzer" },
    { label: "Performance", href: "/dashboard/performance" },
    { label: "Calendar", href: "/dashboard/calendar" },
    { label: "Notifications", href: "/dashboard/notifications" },
    { label: "Admin Console", href: "/admin" },
  ];
  return (
    <div className="fixed inset-0 z-50 lg:hidden">
      <div className="absolute inset-0 bg-black/70" onClick={onClose} />
      <div className="absolute left-0 top-0 h-full w-72 border-r border-border bg-card p-4">
        <div className="mb-4 flex items-center justify-between">
          <span className="text-sm font-semibold">Menu</span>
          <button onClick={onClose} className="text-sm text-muted-foreground">Close</button>
        </div>
        <nav className="space-y-0.5">
          {ALL.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              onClick={onClose}
              className={cn(
                "block rounded-md px-3 py-2 text-sm font-medium",
                pathname === item.href ? "bg-secondary text-foreground" : "text-muted-foreground hover:bg-secondary/60"
              )}
            >
              {item.label}
            </Link>
          ))}
        </nav>
      </div>
    </div>
  );
}
