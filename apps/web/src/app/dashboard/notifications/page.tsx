"use client";
import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";
import { Separator } from "@/components/ui/separator";
import { DemoDataBanner } from "@/components/shared/badges";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";

interface Row { key: string; label: string; description: string; }

const SIGNAL_ROWS: Row[] = [
  { key: "aplusplus", label: "A++ signals", description: "Highest-quality setups only." },
  { key: "aplus", label: "A+ signals", description: "Strong setups, one tier below A++." },
];
const ASSET_ROWS: Row[] = [
  { key: "xauusd", label: "XAU/USD", description: "Gold signal alerts." },
  { key: "eurusd", label: "EUR/USD", description: "Euro signal alerts." },
  { key: "gbpusd", label: "GBP/USD", description: "Cable signal alerts." },
];
const CHANNEL_ROWS: Row[] = [
  { key: "browser", label: "Browser notification", description: "Push notifications via this installed app (PWA)." },
  { key: "telegram", label: "Telegram", description: "Send alerts to a linked Telegram chat." },
  { key: "email", label: "Email", description: "Send alerts to your account email." },
];

export default function NotificationsPage() {
  const [state, setState] = useState<Record<string, boolean>>({
    aplusplus: true, aplus: true, xauusd: true, eurusd: true, gbpusd: true, browser: true, telegram: false, email: false,
  });
  const toggle = (key: string) => setState((s) => ({ ...s, [key]: !s[key] }));

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <div>
        <h1 className="text-xl font-semibold tracking-tight text-foreground">Notifications</h1>
        <p className="text-sm text-muted-foreground">Choose what you get alerted about, and where.</p>
      </div>

      <DemoDataBanner />

      <SettingsGroup title="Signal grades" rows={SIGNAL_ROWS} state={state} toggle={toggle} />
      <SettingsGroup title="Assets" rows={ASSET_ROWS} state={state} toggle={toggle} />
      <SettingsGroup title="Delivery channels" rows={CHANNEL_ROWS} state={state} toggle={toggle} />

      {state.telegram && (
        <Card>
          <CardHeader>
            <CardTitle>Telegram bot</CardTitle>
            <CardDescription>Link your chat to receive alerts. The bot token itself is kept server-side and never exposed here.</CardDescription>
          </CardHeader>
          <CardContent className="flex gap-2">
            <div className="flex-1 space-y-1.5">
              <Label htmlFor="chat-id">Telegram chat ID</Label>
              <Input id="chat-id" placeholder="e.g. 123456789" />
            </div>
            <Button className="mt-6">Save</Button>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function SettingsGroup({ title, rows, state, toggle }: { title: string; rows: Row[]; state: Record<string, boolean>; toggle: (k: string) => void }) {
  return (
    <Card>
      <CardHeader><CardTitle>{title}</CardTitle></CardHeader>
      <CardContent className="space-y-0">
        {rows.map((r, i) => (
          <div key={r.key}>
            {i > 0 && <Separator className="my-3" />}
            <div className="flex items-center justify-between gap-4">
              <div>
                <p className="text-sm font-medium text-foreground">{r.label}</p>
                <p className="text-xs text-muted-foreground">{r.description}</p>
              </div>
              <Switch checked={state[r.key] ?? false} onCheckedChange={() => toggle(r.key)} />
            </div>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}
