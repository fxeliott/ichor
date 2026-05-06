/**
 * PushToggle — UI button to enable/disable PWA push notifications.
 *
 * Flow on enable :
 *   1. Request browser permission (Notification API)
 *   2. Wait for service-worker registration ready
 *   3. Fetch VAPID public key from /v1/push/public-key
 *   4. PushManager.subscribe() with applicationServerKey
 *   5. POST /v1/push/subscribe with the resulting subscription JSON
 *
 * On disable : unsubscribe + POST /v1/push/unsubscribe.
 *
 * Shows minimal status text (denied / disabled / enabled) + spinner
 * while the subscription request is in flight.
 *
 * VISION_2026 — sprint R PWA push.
 */

"use client";

import * as React from "react";

type Status = "loading" | "unsupported" | "denied" | "disabled" | "enabled";

const apiUrl = (path: string) =>
  `${process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000"}${path}`;

const urlBase64ToUint8Array = (b64: string): Uint8Array => {
  const padding = "=".repeat((4 - (b64.length % 4)) % 4);
  const base64 = (b64 + padding).replace(/-/g, "+").replace(/_/g, "/");
  const raw = window.atob(base64);
  const out = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; ++i) out[i] = raw.charCodeAt(i);
  return out;
};

export const PushToggle: React.FC = () => {
  const [status, setStatus] = React.useState<Status>("loading");
  const [error, setError] = React.useState<string | null>(null);

  const refreshStatus = React.useCallback(async () => {
    if (typeof window === "undefined") return;
    if (!("serviceWorker" in navigator) || !("PushManager" in window)) {
      setStatus("unsupported");
      return;
    }
    if (Notification.permission === "denied") {
      setStatus("denied");
      return;
    }
    try {
      const reg = await navigator.serviceWorker.ready;
      const sub = await reg.pushManager.getSubscription();
      setStatus(sub ? "enabled" : "disabled");
    } catch {
      setStatus("disabled");
    }
  }, []);

  React.useEffect(() => {
    refreshStatus();
  }, [refreshStatus]);

  const enable = async () => {
    setError(null);
    try {
      if (Notification.permission === "default") {
        const perm = await Notification.requestPermission();
        if (perm !== "granted") {
          setStatus("denied");
          return;
        }
      }
      const r = await fetch(apiUrl("/v1/push/public-key"));
      if (!r.ok) throw new Error(`public-key ${r.status}`);
      const { public_key } = (await r.json()) as { public_key: string };

      const reg = await navigator.serviceWorker.ready;
      const keyArr = urlBase64ToUint8Array(public_key);
      const sub = await reg.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: keyArr.buffer.slice(
          keyArr.byteOffset,
          keyArr.byteOffset + keyArr.byteLength,
        ) as ArrayBuffer,
      });

      const subJson = sub.toJSON();
      const subBody = await fetch(apiUrl("/v1/push/subscribe"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(subJson),
      });
      if (!subBody.ok) throw new Error(`subscribe ${subBody.status}`);
      setStatus("enabled");
    } catch (e) {
      setError(e instanceof Error ? e.message : "unknown");
    }
  };

  const disable = async () => {
    setError(null);
    try {
      const reg = await navigator.serviceWorker.ready;
      const sub = await reg.pushManager.getSubscription();
      if (sub) {
        await fetch(apiUrl("/v1/push/unsubscribe"), {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ endpoint: sub.endpoint }),
        });
        await sub.unsubscribe();
      }
      setStatus("disabled");
    } catch (e) {
      setError(e instanceof Error ? e.message : "unknown");
    }
  };

  if (status === "loading" || status === "unsupported") {
    return null; // hide cleanly on iOS legacy / no SW support
  }

  return (
    <div className="flex items-center gap-2 text-[11px]">
      {status === "enabled" ? (
        <button
          type="button"
          onClick={disable}
          className="px-2 py-1 rounded border border-emerald-700/60 bg-emerald-900/30 text-emerald-200 hover:bg-emerald-900/50"
          title="Désactiver les notifications push"
        >
          🔔 actives
        </button>
      ) : status === "denied" ? (
        <span
          className="px-2 py-1 rounded border border-red-700/40 bg-red-900/20 text-red-300"
          title="Notifications bloquées au niveau navigateur. Active dans les Réglages du site."
        >
          🔕 bloquées
        </span>
      ) : (
        <button
          type="button"
          onClick={enable}
          className="px-2 py-1 rounded border border-[var(--color-ichor-border-strong)] text-[var(--color-ichor-text-muted)] hover:bg-[var(--color-ichor-surface-2)]"
          title="Activer les push notifications quand une carte approved est générée"
        >
          🔔 activer push
        </button>
      )}
      {error && (
        <span className="text-red-300/80 text-[10px]" role="alert">
          ⚠ {error.slice(0, 40)}
        </span>
      )}
    </div>
  );
};
