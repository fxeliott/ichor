/* Ichor web-push service worker.
 *
 * Minimal and push-focused: it does NOT cache pages (the app is online-only
 * and data freshness matters). Its only job is to receive web-push messages
 * and surface them as OS notifications, then focus/open the right briefing
 * when the user clicks.
 *
 * Payload shape (see apps/api services/push.send_to_all):
 *   { "title": "...", "body": "...", "data": { "url": "/briefing/EUR_USD" } }
 *
 * ADR-017: the notification only DESCRIBES a market event — never an order.
 */

self.addEventListener("install", () => {
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(self.clients.claim());
});

self.addEventListener("push", (event) => {
  let data = {};
  try {
    data = event.data ? event.data.json() : {};
  } catch (_e) {
    data = {};
  }
  const title = data.title || "Ichor";
  const body = data.body || "";
  const url = (data.data && data.data.url) || "/";
  event.waitUntil(
    self.registration.showNotification(title, {
      body,
      icon: "/icon.svg",
      badge: "/icon.svg",
      tag: "ichor-alert",
      renotify: true,
      data: { url },
    }),
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const url = (event.notification.data && event.notification.data.url) || "/";
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((clients) => {
      for (const client of clients) {
        if (client.url.includes(url) && "focus" in client) return client.focus();
      }
      return self.clients.openWindow(url);
    }),
  );
});
