"use client";
import Link from "next/link";
import { Bell, Menu } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel,
  DropdownMenuSeparator, DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { DataStatusPill } from "@/components/shared/badges";
import { useNow } from "@/lib/use-now";
import { formatTimeUTC } from "@/lib/utils";

export function Topbar({ onMenuClick }: { onMenuClick?: () => void }) {
  const now = useNow(1000);

  return (
    <header className="glass sticky top-0 z-30 flex h-14 items-center gap-3 border-b border-border/70 px-4 lg:px-6">
      <Button variant="ghost" size="icon" className="lg:hidden" onClick={onMenuClick} aria-label="Open menu">
        <Menu className="h-5 w-5" />
      </Button>

      <DataStatusPill status="LIVE" />

      <span className="hidden font-mono-tabular text-xs text-muted-foreground sm:inline">
        {now ? formatTimeUTC(now.toISOString()) : "--:--:-- UTC"}
      </span>

      <div className="ml-auto flex items-center gap-2">
        <Link href="/dashboard/notifications">
          <Button variant="ghost" size="icon" aria-label="Notifications" className="relative">
            <Bell className="h-4.5 w-4.5" />
            <span className="absolute right-1.5 top-1.5 h-1.5 w-1.5 rounded-full bg-primary" />
          </Button>
        </Link>

        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button className="flex items-center gap-2 rounded-md px-1.5 py-1 transition-colors hover:bg-secondary/60">
              <Avatar className="h-7 w-7">
                <AvatarFallback>SD</AvatarFallback>
              </Avatar>
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-52">
            <DropdownMenuLabel className="font-normal">
              <p className="text-sm font-medium text-foreground">Shabbir Developer</p>
              <p className="text-xs text-muted-foreground">Free plan</p>
            </DropdownMenuLabel>
            <DropdownMenuSeparator />
            <DropdownMenuItem asChild>
              <Link href="/dashboard/settings">Settings</Link>
            </DropdownMenuItem>
            <DropdownMenuItem asChild>
              <Link href="/dashboard/billing">Billing</Link>
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem asChild>
              <Link href="/login">Sign out</Link>
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </header>
  );
}
