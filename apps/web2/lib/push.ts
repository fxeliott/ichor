/**
 * Web-push subscription helpers (Phase 2 — trader alert notifications).
 *
 * Flow: register the service worker, ask permission, subscribe via the
 * browser PushManager using the server's VAPID public key, then POST the
 * subscription to the API so `send_to_all` can reach this browser.
 *
 * ADR-017: notifications only describe market events, never orders.
 */

export type PushState = "unsupported" | "default" | "granted" | "denied" | "subscribed";

export function pushSupported(): boolean {
  return (
    typeof window !== "undefined" &&
    "serviceWorker" in navigator &&
    "PushManager" in window &&
    "Notification" in window
  );
}

export function currentPermission(): PushState {
  if (!pushSupported()) return "unsupported";
  return Notification.permission as PushState;
}

/** VAPID public keys are URL-safe base64; PushManager needs an
 *  ArrayBuffer-backed Uint8Array (the generic keeps applicationServerKey
 *  happy under the ES2024 lib defs, where a bare Uint8Array widens to
 *  ArrayBufferLike). */
function urlBase64ToUint8Array(base64String: string): Uint8Array<ArrayBuffer> {
  const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
  const raw = atob(base64);
  const buffer = new ArrayBuffer(raw.length);
  const out = new Uint8Array(buffer);
  for (let i = 0; i < raw.length; i += 1) out[i] = raw.charCodeAt(i);
  return out;
}

/**
 * Enable push for this browser. Returns the resulting state. Throws only
 * on a genuine infrastructure failure (VAPID key missing / subscribe POST
 * rejected) so the caller can show an error; permission "denied"/"default"
 * are returned, not thrown.
 */
export async function enablePush(): Promise<PushState> {
  if (!pushSupported()) return "unsupported";

  const permission = await Notification.requestPermission();
  if (permission !== "granted") return permission as PushState;

  const registration = await navigator.serviceWorker.register("/sw.js");
  await navigator.serviceWorker.ready;

  const keyRes = await fetch("/v1/push/public-key", { cache: "no-store" });
  if (!keyRes.ok) throw new Error("VAPID public key unavailable");
  const { public_key: publicKey } = (await keyRes.json()) as { public_key: string };

  const existing = await registration.pushManager.getSubscription();
  const subscription =
    existing ??
    (await registration.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlBase64ToUint8Array(publicKey),
    }));

  const subRes = await fetch("/v1/push/subscribe", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(subscription.toJSON()),
  });
  if (!subRes.ok) throw new Error("subscribe failed");

  return "subscribed";
}
