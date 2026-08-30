/**
 * Browser notifications for new signals.
 *
 * SCOPE, STATED HONESTLY: this uses the Notification API directly, so alerts
 * fire only while NorthFXTrade is actually open — a background tab or the
 * installed PWA window both count, but a fully closed app does not. True
 * background delivery needs Web Push (a VAPID key pair, stored push
 * subscriptions, and a server that sends them), which is not built. The
 * settings page says so rather than implying alerts arrive when they can't.
 *
 * Why that distinction matters here more than in most apps: a 15-minute
 * expiry that a trader sees 20 minutes late is worse than no alert at all,
 * so the app must not overstate when it can reach you.
 */

export type NotificationSupport = NotificationPermission | "unsupported";

export function browserNotificationSupport(): NotificationSupport {
  if (typeof window === "undefined" || !("Notification" in window)) return "unsupported";
  return Notification.permission;
}

export async function requestBrowserNotificationPermission(): Promise<NotificationSupport> {
  if (typeof window === "undefined" || !("Notification" in window)) return "unsupported";
  if (Notification.permission !== "default") return Notification.permission;
  try {
    return await Notification.requestPermission();
  } catch {
    return Notification.permission;
  }
}

export interface SignalAlert {
  id: string;
  asset: string;
  direction: "CALL" | "PUT";
  grade: string;
  expiryMinutes: number | null;
  technicalScore: number;
}

/**
 * Shows one notification. Uses the signal id as the tag so the same signal
 * can never stack up duplicates across re-renders or multiple open tabs.
 */
export function showSignalNotification(alert: SignalAlert): void {
  if (browserNotificationSupport() !== "granted") return;
  const expiry = alert.expiryMinutes ? `${alert.expiryMinutes}m expiry` : "expiry n/a";
  try {
    new Notification(`${alert.grade} ${alert.direction} — ${alert.asset}`, {
      body: `Technical score ${alert.technicalScore}/100 · ${expiry}. Open NorthFXTrade to review before trading.`,
      tag: alert.id,
      icon: "/icons/icon.svg",
      badge: "/icons/icon.svg",
    });
  } catch {
    // Some browsers throw when constructing notifications outside a
    // user-gesture/SW context. Failing to alert must never break the page.
  }
}
