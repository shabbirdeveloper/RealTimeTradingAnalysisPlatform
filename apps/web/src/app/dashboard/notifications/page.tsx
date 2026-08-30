"use client";
import { useCallback, useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { AlertTriangle, Check, BellRing } from "lucide-react";
import {
  loadPreferences, savePreferences, DEFAULT_PREFERENCES,
  type NotificationPreferences,
} from "@/lib/notification-preferences";
import { requestBrowserNotificationPermission, browserNotificationSupport } from "@/lib/browser-notifications";

type PrefKey = keyof Omit<NotificationPreferences, "telegramChatId">;

interface Row { key: PrefKey; label: string; description: string; }

const SIGNAL_ROWS: Row[] = [
  { key: "aplusplusEnabled", label: "A++ signals", description: "Highest-quality setups only." },
  { key: "aplusEnabled", label: "A+ signals", description: "Strong setups, one tier below A++." },
  {
    key: "bgradeEnabled",
    label: "B signals (technical only)",
    description:
      "Currently the ONLY grade the engine can produce — grades are capped at B until a calibrated ML model exists, so leave this off and you'll receive nothing today.",
  },
];
const ASSET_ROWS: Row[] = [
  { key: "xauusdEnabled", label: "XAU/USD", description: "Gold signal alerts." },
  { key: "eurusdEnabled", label: "EUR/USD", description: "Euro signal alerts." },
  { key: "gbpusdEnabled", label: "GBP/USD", description: "Cable signal alerts." },
  { key: "btcusdEnabled", label: "BTC/USD", description: "Bitcoin — trades 24/7, including weekends." },
  { key: "ethusdEnabled", label: "ETH/USD", description: "Ethereum — trades 24/7, including weekends." },
];
const CHANNEL_ROWS: Row[] = [
  { key: "browserEnabled", label: "Browser notification", description: "Alerts while the app is open in a tab or installed window." },
  { key: "telegramEnabled", label: "Telegram", description: "Send alerts to a linked Telegram chat." },
  { key: "emailEnabled", label: "Email", description: "Send alerts to your account email." },
];

export default function NotificationsPage() {
  const [prefs, setPrefs] = useState<NotificationPreferences | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [savedAt, setSavedAt] = useState<number | null>(null);
  const [permission, setPermission] = useState<NotificationPermission | "unsupported">("default");

  useEffect(() => {
    void (async () => {
      const result = await loadPreferences();
      if (result.ok) setPrefs(result.preferences);
      else {
        setLoadError(result.error);
        setPrefs(DEFAULT_PREFERENCES);
      }
    })();
    setPermission(browserNotificationSupport());
  }, []);

  const persist = useCallback(async (next: NotificationPreferences) => {
    setSaving(true);
    setSaveError(null);
    const result = await savePreferences(next);
    setSaving(false);
    if (result.ok) setSavedAt(Date.now());
    else setSaveError(result.error);
  }, []);

  const toggle = (key: PrefKey) => {
    if (!prefs) return;
    const next = { ...prefs, [key]: !prefs[key] };
    setPrefs(next);
    void persist(next);
  };

  const enableBrowserNotifications = async () => {
    const result = await requestBrowserNotificationPermission();
    setPermission(result);
    if (result === "granted" && prefs && !prefs.browserEnabled) {
      const next = { ...prefs, browserEnabled: true };
      setPrefs(next);
      void persist(next);
    }
  };

  if (!prefs) {
    return (
      <div className="mx-auto max-w-2xl space-y-4">
        <Skeleton className="h-8 w-56" />
        <Skeleton className="h-40 w-full" />
        <Skeleton className="h-40 w-full" />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <div>
        <h1 className="text-xl font-semibold tracking-tight text-foreground">Notifications</h1>
        <p className="text-sm text-muted-foreground">Choose what you get alerted about, and where. Changes save automatically.</p>
      </div>

      {loadError && (
        <div className="flex items-start gap-2.5 rounded-lg border border-notrade/30 bg-notrade-muted/50 px-3.5 py-2.5 text-xs text-notrade-foreground">
          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          <span>
            <strong className="font-semibold">Showing defaults, not your saved settings.</strong> {loadError} Changes
            made here may not save until that&apos;s resolved.
          </span>
        </div>
      )}

      <div className="flex h-5 items-center gap-2 text-xs text-muted-foreground">
        {saving && <span>Saving…</span>}
        {!saving && saveError && (
          <span className="flex items-center gap-1.5 text-put">
            <AlertTriangle className="h-3.5 w-3.5" /> {saveError}
          </span>
        )}
        {!saving && !saveError && savedAt && (
          <span className="flex items-center gap-1.5 text-call">
            <Check className="h-3.5 w-3.5" /> Saved
          </span>
        )}
      </div>

      <SettingsGroup title="Signal grades" rows={SIGNAL_ROWS} prefs={prefs} toggle={toggle} />
      <SettingsGroup title="Assets" rows={ASSET_ROWS} prefs={prefs} toggle={toggle} />
      <SettingsGroup title="Delivery channels" rows={CHANNEL_ROWS} prefs={prefs} toggle={toggle} />

      {prefs.browserEnabled && (
        <Card>
          <CardHeader>
            <CardTitle>Browser notifications</CardTitle>
            <CardDescription>
              Alerts fire when a new qualifying signal appears <strong>while NorthFXTrade is open</strong> — in a
              background tab or the installed app. Delivery when the app is fully closed needs a push server, which
              isn&apos;t built yet.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {permission === "unsupported" && (
              <p className="text-sm text-muted-foreground">This browser doesn&apos;t support notifications.</p>
            )}
            {permission === "granted" && (
              <p className="flex items-center gap-1.5 text-sm text-call">
                <Check className="h-4 w-4" /> Permission granted — alerts will show while the app is open.
              </p>
            )}
            {permission === "denied" && (
              <p className="text-sm text-put">
                Permission was blocked in your browser. You&apos;ll need to re-allow notifications for this site in
                your browser settings.
              </p>
            )}
            {permission === "default" && (
              <Button onClick={enableBrowserNotifications} className="gap-2">
                <BellRing className="h-4 w-4" /> Allow browser notifications
              </Button>
            )}
          </CardContent>
        </Card>
      )}

      {prefs.telegramEnabled && (
        <Card>
          <CardHeader>
            <CardTitle>Telegram bot</CardTitle>
            <CardDescription>
              Link your chat to receive alerts. The bot token itself is kept server-side and never exposed here.{" "}
              <strong>Telegram delivery isn&apos;t built yet</strong> — saving a chat ID stores it for when it is.
            </CardDescription>
          </CardHeader>
          <CardContent className="flex gap-2">
            <div className="flex-1 space-y-1.5">
              <Label htmlFor="chat-id">Telegram chat ID</Label>
              <Input
                id="chat-id"
                placeholder="e.g. 123456789"
                value={prefs.telegramChatId ?? ""}
                onChange={(e) => setPrefs({ ...prefs, telegramChatId: e.target.value || null })}
              />
            </div>
            <Button className="mt-6" onClick={() => void persist(prefs)} disabled={saving}>
              Save
            </Button>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function SettingsGroup({
  title, rows, prefs, toggle,
}: {
  title: string;
  rows: Row[];
  prefs: NotificationPreferences;
  toggle: (k: PrefKey) => void;
}) {
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
              <Switch checked={Boolean(prefs[r.key])} onCheckedChange={() => toggle(r.key)} />
            </div>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}
