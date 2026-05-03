/* Ichor PWA service worker — Phase 0 minimal cache shell.
 *
 * Strategy:
 *   - Network-first for HTML (/_next/data, /api proxies, page navigations)
 *     so dashboard data stays fresh.
 *   - Cache-first for static assets (/_next/static, /icon.svg, /manifest...).
 *   - Background sync + push notifications wired in Phase 1+ once VAPID keys exist.
 */

const CACHE_VERSION = "ichor-v1";
const STATIC_ALLOWLIST = [
  "/manifest.webmanifest",
  "/icon.svg",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_VERSION).then((cache) => cache.addAll(STATIC_ALLOWLIST))
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_VERSION).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const { request } = event;
  if (request.method !== "GET") return;

  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;

  // Static assets: cache-first.
  if (url.pathname.startsWith("/_next/static") || STATIC_ALLOWLIST.includes(url.pathname)) {
    event.respondWith(
      caches.match(request).then(
        (hit) =>
          hit ||
          fetch(request).then((res) => {
            const copy = res.clone();
            caches.open(CACHE_VERSION).then((cache) => cache.put(request, copy));
            return res;
          })
      )
    );
    return;
  }

  // HTML / data: network-first with cache fallback for offline.
  event.respondWith(
    fetch(request)
      .then((res) => {
        const copy = res.clone();
        caches.open(CACHE_VERSION).then((cache) => cache.put(request, copy));
        return res;
      })
      .catch(() => caches.match(request).then((hit) => hit || Response.error()))
  );
});

// Phase 1+ push handler stub (silent until VAPID is set up).
self.addEventListener("push", (event) => {
  if (!event.data) return;
  const payload = (() => {
    try {
      return event.data.json();
    } catch {
      return { title: "Ichor", body: event.data.text() };
    }
  })();
  event.waitUntil(
    self.registration.showNotification(payload.title || "Ichor", {
      body: payload.body || "",
      icon: "/icon.svg",
      badge: "/icon.svg",
      tag: payload.tag || "ichor-notification",
      data: payload.data || {},
    })
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const url = event.notification.data?.url || "/";
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((wins) => {
      for (const w of wins) {
        if (w.url === url && "focus" in w) return w.focus();
      }
      if (self.clients.openWindow) return self.clients.openWindow(url);
    })
  );
});
