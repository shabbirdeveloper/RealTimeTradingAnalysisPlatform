"use client";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Download, X } from "lucide-react";

interface BeforeInstallPromptEvent extends Event {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
}

const DISMISSED_KEY = "northfx.install-prompt.dismissed";

/**
 * Registers the service worker and offers the PWA install prompt.
 *
 * The service worker deliberately caches only the app shell, never market
 * data -- see public/sw.js. Installing the app changes how it launches, not
 * what data it trusts: offline still means "no prices shown", never "last
 * known prices shown".
 */
export function PwaProvider() {
  const [installEvent, setInstallEvent] = useState<BeforeInstallPromptEvent | null>(null);
  const [dismissed, setDismissed] = useState(true); // assume dismissed until storage is read

  useEffect(() => {
    if ("serviceWorker" in navigator && process.env.NODE_ENV === "production") {
      // Registered only in production: in dev the SW would cache build assets
      // that change on every edit, which is a confusing debugging experience.
      navigator.serviceWorker.register("/sw.js").catch(() => {
        // Registration failure is non-fatal -- the app works fine without it.
      });
    }

    try {
      setDismissed(localStorage.getItem(DISMISSED_KEY) === "1");
    } catch {
      setDismissed(false); // storage blocked; just show the prompt
    }

    const onBeforeInstall = (event: Event) => {
      event.preventDefault();
      setInstallEvent(event as BeforeInstallPromptEvent);
    };
    window.addEventListener("beforeinstallprompt", onBeforeInstall);
    return () => window.removeEventListener("beforeinstallprompt", onBeforeInstall);
  }, []);

  const install = async () => {
    if (!installEvent) return;
    await installEvent.prompt();
    await installEvent.userChoice;
    setInstallEvent(null);
  };

  const dismiss = () => {
    setInstallEvent(null);
    setDismissed(true);
    try {
      localStorage.setItem(DISMISSED_KEY, "1");
    } catch {
      // Non-essential; worst case the prompt reappears next visit.
    }
  };

  if (!installEvent || dismissed) return null;

  return (
    <div className="fixed bottom-4 left-1/2 z-50 w-[calc(100%-2rem)] max-w-md -translate-x-1/2 rounded-lg border border-border bg-card p-3.5 shadow-lg">
      <div className="flex items-start gap-3">
        <Download className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
        <div className="flex-1">
          <p className="text-sm font-medium text-foreground">Install NorthFXTrade</p>
          <p className="mt-0.5 text-xs text-muted-foreground">
            Launch it like an app and get signal alerts while it&apos;s running.
          </p>
        </div>
        <button onClick={dismiss} aria-label="Dismiss" className="text-muted-foreground hover:text-foreground">
          <X className="h-4 w-4" />
        </button>
      </div>
      <Button onClick={install} size="sm" className="mt-3 w-full">
        Install
      </Button>
    </div>
  );
}
