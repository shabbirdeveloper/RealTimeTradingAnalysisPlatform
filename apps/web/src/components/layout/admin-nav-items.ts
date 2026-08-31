import type { LucideIcon } from "lucide-react";
import {
  Gauge, Radio, Boxes, FlaskConical, Database, Newspaper, Users, CreditCard, HeartPulse, ScrollText, ArrowLeft,
  SlidersHorizontal,
} from "lucide-react";
import type { NavItem } from "./nav-items";

export const ADMIN_NAV: NavItem[] = [
  { label: "Overview", href: "/admin", icon: Gauge },
  { label: "Signals", href: "/admin/signals", icon: Radio },
  { label: "Strategy", href: "/admin/strategy", icon: SlidersHorizontal },
  { label: "Models", href: "/admin/models", icon: Boxes },
  { label: "Backtesting", href: "/admin/backtesting", icon: FlaskConical },
  { label: "Market Data", href: "/admin/market-data", icon: Database },
  { label: "News", href: "/admin/news", icon: Newspaper },
  { label: "Users", href: "/admin/users", icon: Users },
  { label: "Subscriptions", href: "/admin/subscriptions", icon: CreditCard },
  { label: "System", href: "/admin/system", icon: HeartPulse },
  { label: "Logs", href: "/admin/logs", icon: ScrollText },
];

export const BACK_TO_APP: NavItem = { label: "Back to app", href: "/dashboard", icon: ArrowLeft };
