"use client";
import { useEffect, useRef } from "react";
import type { AssetSymbol, Signal } from "@/types";
import { ASSET_CONFIGS } from "@/data/assets";
import { showSignalNotification } from "@/lib/browser-notifications";
import { loadPreferences, type NotificationPreferences } from "@/lib/notification-preferences";

const ASSET_PREF_KEY: Record<AssetSymbol, keyof NotificationPreferences> = {
  XAUUSD: "xauusdEnabled",
  EURUSD: "eurusdEnabled",
  GBPUSD: "gbpusdEnabled",
  BTCUSD: "btcusdEnabled",
  ETHUSD: "ethusdEnabled",
};

function gradeAllowed(grade: string, prefs: NotificationPreferences): boolean {
  if (grade === "A++") return prefs.aplusplusEnabled;
  if (grade === "A+") return prefs.aplusEnabled;
  // B is currently the only grade the engine can emit -- grades are capped
  // there until a calibrated ML model exists (spec section 10). It's opt-in
  // and defaults off, since a B is explicitly not a high-conviction setup
  // and alerting on it by default would train the user to ignore alerts.
  if (grade === "B") return prefs.bgradeEnabled;
  return false;
}

/**
 * Fires a browser notification when a new qualifying signal appears while
 * the app is open. Renders nothing.
 *
 * Only alerts on signals it hasn't already announced (tracked by id), so a
 * re-render or a repeated server poll can't re-notify for the same setup.
 */
export function SignalAlerts({ signals }: { signals: Record<AssetSymbol, Signal | null> }) {
  const announced = useRef<Set<string>>(new Set());
  const prefs = useRef<NotificationPreferences | null>(null);

  useEffect(() => {
    void (async () => {
      const result = await loadPreferences();
      if (result.ok) prefs.current = result.preferences;
    })();
  }, []);

  useEffect(() => {
    const preferences = prefs.current;
    if (!preferences || !preferences.browserEnabled) return;

    for (const [asset, signal] of Object.entries(signals) as [AssetSymbol, Signal | null][]) {
      if (!signal) continue;
      if (signal.direction === "NO_TRADE") continue;
      if (announced.current.has(signal.id)) continue;
      if (!preferences[ASSET_PREF_KEY[asset]]) continue;
      if (!gradeAllowed(signal.grade, preferences)) continue;

      announced.current.add(signal.id);
      showSignalNotification({
        id: signal.id,
        asset: ASSET_CONFIGS[asset].displayName,
        direction: signal.direction,
        grade: signal.grade,
        expiryMinutes: signal.expiryMinutes,
        technicalScore: signal.technicalScore,
      });
    }
  }, [signals]);

  return null;
}
