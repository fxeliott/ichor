"use client";

/**
 * NotificationToggle — opt into trader-alert web-push notifications.
 *
 * One small button. Hidden entirely when the browser doesn't support push.
 * On click it asks permission, registers the service worker and subscribes
 * (see lib/push). Critical alerts (hard scenario invalidations, crisis-level
 * macro moves) then arrive even when the tab is closed.
 *
 * ADR-017: the notifications describe market events, never orders.
 */

import { type ReactElement, useEffect, useState } from "react";

import { currentPermission, enablePush, pushSupported, type PushState } from "@/lib/push";

export function NotificationToggle(): ReactElement | null {
  const [state, setState] = useState<PushState>("unsupported");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!pushSupported()) {
      setState("unsupported");
      return;
    }
    setState(currentPermission());
  }, []);

  if (state === "unsupported") return null;

  const enabled = state === "subscribed" || state === "granted";
  const blocked = state === "denied";

  const label = busy
    ? "Activation…"
    : enabled
      ? "Alertes activées"
      : blocked
        ? "Alertes bloquées par le navigateur"
        : "Activer les alertes";

  const onClick = async () => {
    if (busy || enabled || blocked) return;
    setBusy(true);
    try {
      setState(await enablePush());
    } catch {
      // Infra failure (VAPID/subscribe) — surface as the default state so
      // the user can retry; never throw out of a click handler.
      setState(currentPermission());
    } finally {
      setBusy(false);
    }
  };

  return (
    <button
      type="button"
      onClick={onClick}
      disabled={busy || enabled || blocked}
      aria-live="polite"
      title={
        blocked
          ? "Réactivez les notifications pour ce site dans les réglages du navigateur."
          : "Recevoir une notification quand un évènement de marché majeur survient."
      }
      className="inline-flex items-center gap-2 rounded-full border border-[var(--color-border-subtle)] bg-[var(--color-bg-surface)]/40 px-3 py-1.5 text-xs text-[var(--color-text-secondary)] backdrop-blur-xl transition-colors hover:text-[var(--color-text-primary)] disabled:cursor-default disabled:opacity-70"
    >
      <span aria-hidden="true">{enabled ? "🔔" : blocked ? "🔕" : "🔔"}</span>
      <span>{label}</span>
    </button>
  );
}
