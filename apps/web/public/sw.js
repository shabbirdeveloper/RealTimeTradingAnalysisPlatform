/*
 * NorthFXTrade service worker.
 *
 * THE ONE RULE THAT MATTERS (spec section 27: "Do not cache stale trading
 * data as if it were live"):
 *
 *   Cache the application SHELL. Never cache market data, signals, prices,
 *   or anything that could be served back later as though it were current.
 *
 * A cached price is worse than no price. A trader glancing at an offline
 * dashboard showing yesterday's gold quote, with no indication it is stale,
 * could place a real trade on it. So every navigation and data request is
 * network-first and, when the network fails, the user gets an explicit
 * offline page rather than a plausible-looking stale one.
 *
 * What is cached: static build assets (JS/CSS/fonts/icons) which are
 * content-hashed and therefore safe, plus the offline fallback page.
 */

const VERSION = "v1";
const SHELL_CACHE = `northfx-shell-${VERSION}`;
const OFFLINE_URL = "/offline.html";

// Anything under these paths is data, never cached, always network-only.
const NEVER_CACHE = [
  "/api/",
  "/auth/",
  "/rest/v1/",       // Supabase REST
  "/realtime/v1/",   // Supabase Realtime
];

const PRECACHE = [OFFLINE_URL, "/icons/icon.svg", "/manifest.webmanifest"];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(SHELL_CACHE)
      .then((cache) => cache.addAll(PRECACHE))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(keys.filter((k) => k !== SHELL_CACHE).map((k) => caches.delete(k)))
      )
      .then(() => self.clients.claim())
  );
});

function isNeverCached(url) {
  return NEVER_CACHE.some((prefix) => url.pathname.startsWith(prefix)) ||
    url.hostname.endsWith(".supabase.co");
}

self.addEventListener("fetch", (event) => {
  const { request } = event;

  // Only GET is ever cacheable; mutations must always hit the network.
  if (request.method !== "GET") return;

  const url = new URL(request.url);

  // Cross-origin and all data endpoints: straight to the network, no cache
  // read and no cache write. If it fails, it fails honestly.
  if (url.origin !== self.location.origin || isNeverCached(url)) return;

  // Page navigations: network-first, falling back to an explicit offline
  // page. Never a cached dashboard -- see the header comment.
  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request).catch(async () => {
        const cache = await caches.open(SHELL_CACHE);
        const offline = await cache.match(OFFLINE_URL);
        return offline ?? Response.error();
      })
    );
    return;
  }

  // Build assets are content-hashed, so a cache hit can never be stale in a
  // meaningful way. Cache-first here is what makes the app load offline and
  // start fast.
  const isBuildAsset =
    url.pathname.startsWith("/_next/static/") ||
    url.pathname.startsWith("/icons/") ||
    /\.(?:css|js|woff2?|png|svg|ico)$/.test(url.pathname);

  if (!isBuildAsset) return;

  event.respondWith(
    caches.match(request).then((cached) => {
      if (cached) return cached;
      return fetch(request).then((response) => {
        if (response && response.status === 200 && response.type === "basic") {
          const copy = response.clone();
          caches.open(SHELL_CACHE).then((cache) => cache.put(request, copy));
        }
        return response;
      });
    })
  );
});

// Web Push is intentionally NOT handled here. Implementing `push` without a
// server that actually sends notifications would create a handler that can
// never fire -- see apps/web/src/lib/browser-notifications.ts for what real
// background delivery still requires.
