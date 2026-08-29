import Link from "next/link";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Check } from "lucide-react";

const PLANS = [
  { name: "Free", price: "$0", period: "forever", features: ["Delayed signals", "1 asset", "Community support"], cta: "Start free" },
  { name: "Pro", price: "$49", period: "/month", features: ["Live A++/A+ signals", "All 3 assets", "Telegram + email alerts", "Full history & performance"], highlight: true, cta: "Start Pro" },
  { name: "Institutional", price: "Custom", period: "", features: ["API access", "Priority support", "Custom model tuning"], cta: "Contact us" },
];

export default function PricingPage() {
  return (
    <div className="container py-16">
      <div className="max-w-xl">
        <h1 className="text-3xl font-semibold text-foreground">Simple, transparent pricing</h1>
        <p className="mt-3 text-muted-foreground">No performance guarantees are sold at any tier — you&apos;re paying for analysis infrastructure, not promises.</p>
      </div>
      <div className="mt-10 grid grid-cols-1 gap-4 md:grid-cols-3">
        {PLANS.map((plan) => (
          <Card key={plan.name} className={plan.highlight ? "border-primary/50" : undefined}>
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle>{plan.name}</CardTitle>
                {plan.highlight && <Badge>Popular</Badge>}
              </div>
              <CardDescription>
                <span className="font-mono-tabular text-2xl font-semibold text-foreground">{plan.price}</span>
                <span className="text-sm text-muted-foreground">{plan.period}</span>
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <ul className="space-y-2 text-sm text-muted-foreground">
                {plan.features.map((f) => (
                  <li key={f} className="flex items-center gap-2"><Check className="h-3.5 w-3.5 text-primary" /> {f}</li>
                ))}
              </ul>
              <Link href="/register">
                <Button variant={plan.highlight ? "default" : "outline"} className="w-full">{plan.cta}</Button>
              </Link>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
