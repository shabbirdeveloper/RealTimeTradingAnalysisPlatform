import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { DemoDataBanner } from "@/components/shared/badges";
import { Check } from "lucide-react";

const PLANS = [
  { name: "Free", price: "$0", features: ["Delayed signals", "1 asset", "Community support"] },
  { name: "Pro", price: "$49/mo", features: ["Live A++/A+ signals", "All 3 assets", "Telegram + email alerts", "Full history & performance"], highlight: true },
  { name: "Institutional", price: "Contact us", features: ["API access", "Priority support", "Custom model tuning"] },
];

export default function BillingPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold tracking-tight text-foreground">Billing</h1>
        <p className="text-sm text-muted-foreground">You are currently on the Free plan.</p>
      </div>

      <DemoDataBanner />

      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        {PLANS.map((plan) => (
          <Card key={plan.name} className={plan.highlight ? "border-primary/50" : undefined}>
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle>{plan.name}</CardTitle>
                {plan.highlight && <Badge>Popular</Badge>}
              </div>
              <CardDescription className="font-mono-tabular text-xl font-semibold text-foreground">{plan.price}</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <ul className="space-y-2 text-sm text-muted-foreground">
                {plan.features.map((f) => (
                  <li key={f} className="flex items-center gap-2">
                    <Check className="h-3.5 w-3.5 text-primary" /> {f}
                  </li>
                ))}
              </ul>
              <Button variant={plan.highlight ? "default" : "outline"} className="w-full" disabled>
                {plan.name === "Free" ? "Current plan" : "Coming soon"}
              </Button>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
