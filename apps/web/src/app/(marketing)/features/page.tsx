import { Card, CardContent } from "@/components/ui/card";
import {
  LayoutGrid, GitBranch, Newspaper, Brain, Gauge, History, BellRing, Smartphone,
} from "lucide-react";

const FEATURES = [
  { icon: LayoutGrid, title: "Three focused assets", desc: "XAU/USD, EUR/USD, GBP/USD — each with independently tuned configuration rather than one-size-fits-all rules." },
  { icon: GitBranch, title: "Regime-aware logic", desc: "Trending, ranging, high/low volatility, news mode and unstable regimes each apply different signal rules." },
  { icon: Newspaper, title: "News protection", desc: "High-impact CPI, NFP, FOMC, ECB and BoE events trigger a configurable pre/post blackout window." },
  { icon: Brain, title: "Direction + meta model", desc: "A direction model estimates probability; a separate meta model decides TAKE or REJECT to cut false positives." },
  { icon: Gauge, title: "Calibrated confidence", desc: "Confidence percentages come from calibrated model outputs — never faked. Missing models show MODEL_NOT_READY." },
  { icon: History, title: "Walk-forward backtesting", desc: "Train / validate / walk-forward / unseen test / demo forward test, with zero look-ahead bias." },
  { icon: BellRing, title: "Notifications", desc: "Browser push, Telegram and email alerts, filterable by asset and grade." },
  { icon: Smartphone, title: "Installable PWA", desc: "Works offline with a clear LIVE / DELAYED / OFFLINE status — never shows stale data as live." },
];

export default function FeaturesPage() {
  return (
    <div className="container py-16">
      <div className="max-w-2xl">
        <h1 className="text-3xl font-semibold text-foreground">Built like a quant terminal, not a signal spam bot</h1>
        <p className="mt-3 text-muted-foreground">Every module exists to reduce false positives, not increase signal count.</p>
      </div>
      <div className="mt-10 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {FEATURES.map((f) => (
          <Card key={f.title}>
            <CardContent className="space-y-3 p-5">
              <span className="flex h-9 w-9 items-center justify-center rounded-md bg-primary/10 text-primary">
                <f.icon className="h-4.5 w-4.5" />
              </span>
              <p className="text-sm font-medium text-foreground">{f.title}</p>
              <p className="text-xs text-muted-foreground">{f.desc}</p>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
