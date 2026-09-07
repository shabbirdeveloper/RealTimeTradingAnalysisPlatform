import type { LucideIcon } from "lucide-react";
import {
  LayoutDashboard, Radio, LineChart, SlidersHorizontal, History,
  BarChart3, CalendarClock, Bell, Settings, CreditCard, Cpu,
} from "lucide-react";

export interface NavItem {
  label: string;
  href: string;
  icon: LucideIcon;
}

export const DASHBOARD_NAV: NavItem[] = [
  { label: "Dashboard", href: "/dashboard", icon: LayoutDashboard },
  { label: "Live Signals", href: "/dashboard/signals", icon: Radio },
  // Placed high deliberately: on a selective engine the declines ARE the
  // output, and burying them leaves the product looking idle.
  { label: "Engine", href: "/dashboard/engine", icon: Cpu },
  { label: "Markets", href: "/dashboard/markets/xauusd", icon: LineChart },
  { label: "Analyzer", href: "/dashboard/analyzer", icon: SlidersHorizontal },
  { label: "History", href: "/dashboard/history", icon: History },
  { label: "Performance", href: "/dashboard/performance", icon: BarChart3 },
  { label: "Calendar", href: "/dashboard/calendar", icon: CalendarClock },
  { label: "Notifications", href: "/dashboard/notifications", icon: Bell },
  { label: "Settings", href: "/dashboard/settings", icon: Settings },
];

export const MOBILE_NAV: NavItem[] = [
  { label: "Home", href: "/dashboard", icon: LayoutDashboard },
  { label: "Signals", href: "/dashboard/signals", icon: Radio },
  { label: "Markets", href: "/dashboard/markets/xauusd", icon: LineChart },
  { label: "History", href: "/dashboard/history", icon: History },
  { label: "Settings", href: "/dashboard/settings", icon: Settings },
];

export const MARKET_LINKS = [
  { label: "XAU/USD", href: "/dashboard/markets/xauusd" },
  { label: "EUR/USD", href: "/dashboard/markets/eurusd" },
  { label: "GBP/USD", href: "/dashboard/markets/gbpusd" },
  { label: "BTC/USD", href: "/dashboard/markets/btcusd" },
  { label: "ETH/USD", href: "/dashboard/markets/ethusd" },
];
