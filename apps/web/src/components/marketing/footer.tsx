import Link from "next/link";
import { Logo } from "@/components/layout/logo";

const COLUMNS = [
  { title: "Product", links: [{ label: "Features", href: "/features" }, { label: "Performance", href: "/performance" }, { label: "Pricing", href: "/pricing" }] },
  { title: "Account", links: [{ label: "Log in", href: "/login" }, { label: "Register", href: "/register" }, { label: "Dashboard", href: "/dashboard" }] },
  { title: "Legal", links: [{ label: "Disclaimer", href: "/disclaimer" }, { label: "Privacy Policy", href: "/privacy" }, { label: "Terms of Service", href: "/terms" }] },
];

export function MarketingFooter() {
  return (
    <footer className="border-t border-border">
      <div className="container grid grid-cols-2 gap-8 py-12 md:grid-cols-4">
        <div className="col-span-2 md:col-span-1">
          <Logo />
          <p className="mt-3 max-w-xs text-sm text-muted-foreground">
            Algorithmic market analysis for manual execution. Not a broker, not an auto-trader.
          </p>
        </div>
        {COLUMNS.map((col) => (
          <div key={col.title}>
            <p className="text-sm font-medium text-foreground">{col.title}</p>
            <ul className="mt-3 space-y-2">
              {col.links.map((l) => (
                <li key={l.href}>
                  <Link href={l.href} className="text-sm text-muted-foreground hover:text-foreground">{l.label}</Link>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
      <div className="border-t border-border py-6">
        <p className="container text-xs text-muted-foreground">
          © {new Date().getFullYear()} NorthFXTrade. Trading involves substantial risk of loss. Historical or simulated performance does not guarantee future results.
        </p>
      </div>
    </footer>
  );
}
