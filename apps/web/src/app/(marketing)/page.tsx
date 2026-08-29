import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { DirectionBadge, GradeBadge, RegimeBadge } from "@/components/shared/badges";
import { AnimatedNumber } from "@/components/shared/animated-number";
import { ArrowRight, ShieldCheck, Filter, LineChart, TrendingUp, AlertTriangle } from "lucide-react";

export default function LandingPage() {
  return (
    <div>
      <section className="relative overflow-hidden border-b border-border/70 bg-grid">
        <div className="hero-float pointer-events-none absolute inset-x-0 top-0 h-[520px] bg-[radial-gradient(ellipse_760px_420px_at_50%_-10%,hsl(var(--primary)/0.16),transparent_65%)]" />
        <div className="container relative flex flex-col items-center gap-7 py-24 text-center md:py-32">
          <span className="animate-in fade-in-0 slide-in-from-bottom-2 duration-500 ease-out inline-flex items-center gap-1.5 rounded-full border border-primary/25 bg-primary/10 px-3 py-1 text-xs font-medium text-primary">
            <ShieldCheck className="h-3.5 w-3.5" /> Informational analysis only — manual execution
          </span>
          <h1
            className="max-w-3xl animate-in fade-in-0 slide-in-from-bottom-3 text-5xl font-semibold leading-[1.08] tracking-tight duration-700 ease-out md:text-6xl"
            style={{ animationDelay: "80ms" }}
          >
            <span className="text-gradient-primary">Reject weak setups.</span>
            <br />
            Surface only the ones worth trading.
          </h1>
          <p
            className="max-w-xl animate-in fade-in-0 slide-in-from-bottom-3 text-balance text-base text-muted-foreground duration-700 ease-out md:text-lg"
            style={{ animationDelay: "160ms" }}
          >
            NorthFXTrade analyzes XAU/USD, EUR/USD and GBP/USD across four timeframes and returns CALL, PUT, or
            NO TRADE — never a forced signal. You review it, then execute manually on your own platform.
          </p>
          <div
            className="flex animate-in fade-in-0 slide-in-from-bottom-3 flex-wrap items-center justify-center gap-3 duration-700 ease-out"
            style={{ animationDelay: "240ms" }}
          >
            <Link href="/register"><Button size="lg" className="gap-1.5">Get started <ArrowRight className="h-4 w-4" /></Button></Link>
            <Link href="/dashboard"><Button size="lg" variant="outline">View live dashboard</Button></Link>
          </div>
          <div
            className="mt-6 flex animate-in fade-in-0 flex-wrap items-center justify-center gap-x-10 gap-y-4 duration-700 ease-out"
            style={{ animationDelay: "320ms" }}
          >
            <Stat value={3} label="Focused assets" />
            <div className="hidden h-8 w-px bg-border sm:block" />
            <Stat value={4} label="Analysis timeframes" />
            <div className="hidden h-8 w-px bg-border sm:block" />
            <Stat value={3} label="Expiries" />
            <div className="hidden h-8 w-px bg-border sm:block" />
            <Stat value="A++" label="Highest signal grade" accent />
          </div>
        </div>
      </section>

      <section className="container grid grid-cols-1 gap-4 py-16 md:grid-cols-3">
        <FeatureCard index={0} icon={Filter} title="Quality over quantity" desc="Most analysis cycles end in NO TRADE. Only setups that clear technical, regime, and meta-model filters surface as A/A+/A++." />
        <FeatureCard index={1} icon={LineChart} title="Multi-timeframe confluence" desc="H4 macro context down to M5 entry timing — signals need alignment, not just one indicator crossing a line." />
        <FeatureCard index={2} icon={TrendingUp} title="Verified performance, not claims" desc="Overall accuracy and A++ accuracy are tracked separately from real recorded results. No hard-coded win rates." />
      </section>

      <section className="border-y border-border bg-card/30 py-16">
        <div className="container grid grid-cols-1 items-center gap-10 md:grid-cols-2">
          <div>
            <h2 className="text-2xl font-semibold text-foreground">Two outcomes look like this</h2>
            <p className="mt-2 text-muted-foreground">Illustrative examples — not live data.</p>
          </div>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Card className="aplusplus-frame overflow-hidden border-aplusplus/30">
              <div className="h-[3px] w-full bg-call" />
              <CardContent className="space-y-3 p-5">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-semibold">XAU/USD</span>
                  <RegimeBadge regime="TRENDING_UP" />
                </div>
                <DirectionBadge direction="CALL" />
                <div className="flex items-end justify-between border-t border-border/70 pt-3">
                  <div>
                    <p className="text-[10.5px] font-medium uppercase tracking-wider text-muted-foreground">Confidence</p>
                    <p className="font-mono-tabular text-lg font-semibold">92.4%</p>
                  </div>
                  <GradeBadge grade="A++" />
                </div>
              </CardContent>
            </Card>
            <Card className="overflow-hidden">
              <div className="h-[3px] w-full bg-notrade/70" />
              <CardContent className="space-y-3 p-5">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-semibold">EUR/USD</span>
                  <RegimeBadge regime="RANGING" />
                </div>
                <DirectionBadge direction="NO_TRADE" />
                <p className="text-xs text-muted-foreground">Market conditions not strong enough.</p>
              </CardContent>
            </Card>
          </div>
        </div>
      </section>

      <section className="container py-16">
        <div className="flex items-start gap-3 rounded-lg border border-notrade/25 bg-notrade-muted/50 p-5">
          <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-notrade" />
          <p className="text-sm text-notrade-foreground/90">
            This platform provides algorithmic market analysis and informational trading signals. Trading involves
            substantial risk. Historical or simulated performance does not guarantee future results. Read the full{" "}
            <Link href="/disclaimer" className="underline">disclaimer</Link>.
          </p>
        </div>
      </section>
    </div>
  );
}

function Stat({ value, label, accent }: { value: string | number; label: string; accent?: boolean }) {
  return (
    <div className="text-center">
      <p className={`font-mono-tabular text-2xl font-bold tracking-tight ${accent ? "text-aplusplus" : "text-foreground"}`}>
        {typeof value === "number" ? <AnimatedNumber value={value} decimals={0} duration={900} /> : value}
      </p>
      <p className="text-[11px] uppercase tracking-wider text-muted-foreground">{label}</p>
    </div>
  );
}

function FeatureCard({ icon: Icon, title, desc, index = 0 }: { icon: typeof Filter; title: string; desc: string; index?: number }) {
  return (
    <Card
      className="card-premium-hover animate-in fade-in-0 slide-in-from-bottom-4 duration-500 ease-out"
      style={{ animationDelay: `${index * 100}ms` }}
    >
      <CardContent className="space-y-3 p-6">
        <span className="flex h-10 w-10 items-center justify-center rounded-lg bg-gradient-to-br from-primary/20 to-primary/5 text-primary ring-1 ring-inset ring-primary/20">
          <Icon className="h-5 w-5" />
        </span>
        <p className="font-semibold text-foreground">{title}</p>
        <p className="text-sm text-muted-foreground">{desc}</p>
      </CardContent>
    </Card>
  );
}
