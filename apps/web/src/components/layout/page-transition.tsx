"use client";
import { usePathname } from "next/navigation";

/**
 * Wraps route content so navigating between pages replays a subtle
 * fade/slide-in instead of content just snapping into place. Keyed by
 * pathname so it remounts (and therefore re-animates) on every navigation,
 * while in-place re-renders from ticking clocks/data refreshes do not
 * retrigger it.
 */
export function PageTransition({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  return (
    <div key={pathname} className="animate-in fade-in slide-in-from-bottom-2 duration-500 ease-out">
      {children}
    </div>
  );
}
