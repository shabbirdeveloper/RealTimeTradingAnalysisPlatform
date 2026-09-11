import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { AnimatedNumber } from "@/components/shared/animated-number";
import { SignalPreview } from "@/components/marketing/signal-preview";
import { getPublicPreview, getPublicPerformance } from "@/lib/public-preview";
import { ArrowRight, ShieldCheck, Filter, LineChart, TrendingUp, AlertTriangle } from "lucide-react";

export const dynamic = "force-dynamic";

export default async function LandingPage() {
  const [preview, performance] = await Promise.all([
    getPublicPreview(),
    getPublicPerformance(),
  ]);

  return (
    <div>
      <section className="relative overflow-hidden border-b border-border/70">
        <div className="bg-grid pointer-events-none absolute inset-0" />
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
            NorthFXTrade analyzes XAU/USD across four timeframes and returns CALL, PUT, or NO TRADE —
            never a forced signal. You review it, then execute manually on your own platform.
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
            <Stat value={1} label="Focused asset" />
            <div className="hidden h-8 w-px bg-border sm:block" />
            <Stat value={4} label="Analysis timeframes" />
            <div className="hidden h-8 w-px bg-border sm:block" />
            <Stat value={3} label="Expiries" />
            <div className="hidden h-8 w-px bg-border sm:block" />
            {performance.available ? (
              <Stat value={performance.resolved} label="Signals resolved" accent />
            ) : (
              <Stat value="—" label="Signals resolved" />
            )}
          </div>
        </div>
      </section>

      <section className="container grid grid-cols-1 gap-4 py-16 md:grid-cols-3">
        <FeatureCard index={0} icon={Filter} title="Quality over quantity" desc="Most analysis cycles end in NO TRADE. A setup has to clear data freshness, timeframe agreement, directional separation, regime and quality before it surfaces at all." />
        <FeatureCard index={1} icon={LineChart} title="Multi-timeframe confluence" desc="H4 macro context down to M5 entry timing. CALL and PUT are scored independently and must separate — a market that merely leans is refused." />
        <FeatureCard index={2} icon={TrendingUp} title="Verified performance, not claims" desc="Accuracy is computed from resolved signals and published with its sample size and confidence interval — including when the answer is that it is too early to tell." />
      </section>

      <section className="border-y border-border bg-card/30 py-16">
        <div className="container grid grid-cols-1 items-start gap-10 md:grid-cols-2">
          <div className="space-y-4">
            <h2 className="text-2xl font-semibold text-foreground">This is the engine, right now</h2>
            <p className="text-muted-foreground">
              Not a demo. The panel beside this reads the live decision for each asset —
              including, most of the time, no decision at all.
            </p>
            <p className="text-sm text-muted-foreground">
              When a signal is open you will see that it exists and what quality it reached.
              The direction and entry price stay behind the login, because that is the product.
            </p>

            <div className="space-y-3 rounded-lg border border-border bg-background/60 p-5">
              <p className="text-[10.5px] font-medium uppercase tracking-wider text-muted-foreground">
                Measured performance
              </p>

              {!performance.available ? (
                <>
                  <p className="font-mono-tabular text-2xl font-semibold text-muted-foreground">
                    Not available
                  </p>
                  <p className="text-sm text-muted-foreground">
                    Performance figures cannot be read right now. This is a connection or
                    setup problem on our side, not a result — a zero here would have been a
                    claim, and we would rather say nothing than say something untrue.
                  </p>
                </>
              ) : performance.resolved < 30 ? (
                <>
                  <p className="font-mono-tabular text-2xl font-semibold text-foreground">
                    Too early to say
                  </p>
                  <p className="text-sm text-muted-foreground">
                    {performance.resolved === 0
                      ? "No signal has run to expiry yet."
                      : `${performance.resolved} signals have resolved (${performance.wins}W / ${performance.losses}L).`}{" "}
                    A win rate needs about 30 before it means anything — below that, one trade
                    moves it ten points.
                  </p>
                </>
              ) : (
                <>
                  <p className="font-mono-tabular text-2xl font-semibold text-foreground">
                    {performance.accuracy}%
                    <span className="ml-2 text-sm font-normal text-muted-foreground">
                      {performance.interval &&
                        `${performance.interval.low.toFixed(1)}–${performance.interval.high.toFixed(1)}`}
                    </span>
                  </p>
                  <p className="text-sm text-muted-foreground">
                    From {performance.resolved} resolved signals ({performance.wins}W / {performance.losses}L).
                    The range is the 95% interval — the honest width of what this sample can show.
                  </p>
                  <p className="text-sm">
                    {performance.verdict === "ABOVE_BREAK_EVEN" ? (
                      <span className="text-call">
                        Above the {performance.breakEven.toFixed(1)}% needed to break even at an 80% payout.
                      </span>
                    ) : performance.verdict === "BELOW_BREAK_EVEN" ? (
                      <span className="text-put">
                        Below the {performance.breakEven.toFixed(1)}% needed to break even at an 80% payout.
                        We are not claiming this is profitable yet, because it is not.
                      </span>
                    ) : (
                      <span className="text-notrade">
                        Not yet distinguishable from the {performance.breakEven.toFixed(1)}% needed to break
                        even at an 80% payout.
                      </span>
                    )}
                  </p>
                </>
              )}

              <p className="border-t border-border pt-3 text-xs text-muted-foreground">
                Every figure on this page is computed from recorded results. We publish the sample
                size and the interval with the rate, so you can see how much it is worth. No
                advertised accuracy, no target we have not reached.
              </p>
            </div>
          </div>

          <SignalPreview rows={preview} />
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
