"use client";

/**
 * useLiveEvents — subscribe to the dashboard WebSocket and surface a small
 * toast/badge whenever a new briefing / alert / bias signal lands.
 *
 * Strategy:
 *   - Open a single WS to /v1/ws/dashboard on mount.
 *   - On message, push a normalized event into local React state (max 5 kept).
 *   - Auto-reconnect with exponential backoff (1s → 16s cap) on close/error.
 *   - When we receive a `briefings:new` event, call router.refresh() so the
 *     server-rendered list re-fetches without a full page reload.
 *
 * The component using this hook can render the events however it wants —
 * see `LiveEventsToast` in `app/live-events-toast.tsx`.
 */

import { useEffect, useRef, useState, useCallback } from "react";
import { useRouter } from "next/navigation";

export type LiveEventChannel =
  | "ichor:briefings:new"
  | "ichor:alerts:new"
  | "ichor:bias:updated";

export interface LiveEvent {
  /** Local-only id for React keys / dismissal. */
  localId: string;
  channel: LiveEventChannel;
  data: Record<string, unknown>;
  receivedAt: number;
}

export interface UseLiveEventsOptions {
  /** Override WS URL. Default: derived from NEXT_PUBLIC_API_URL. */
  url?: string;
  /** Max events kept in local buffer (oldest evicted). Default 5. */
  bufferSize?: number;
  /** Channels to refresh the router on. Default: briefings + alerts. */
  refreshOn?: LiveEventChannel[];
}

const DEFAULT_REFRESH: LiveEventChannel[] = [
  "ichor:briefings:new",
  "ichor:alerts:new",
];

const wsUrlFromApi = (apiUrl: string): string => {
  // Convert http(s)://host → ws(s)://host/v1/ws/dashboard
  try {
    const u = new URL(apiUrl);
    u.protocol = u.protocol === "https:" ? "wss:" : "ws:";
    u.pathname = "/v1/ws/dashboard";
    u.search = "";
    return u.toString();
  } catch {
    return "ws://127.0.0.1:8000/v1/ws/dashboard";
  }
};

export function useLiveEvents(options: UseLiveEventsOptions = {}) {
  const router = useRouter();
  const [events, setEvents] = useState<LiveEvent[]>([]);
  const [connected, setConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const backoffRef = useRef(1000);
  const cancelledRef = useRef(false);
  const heartbeatRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const dismiss = useCallback((localId: string) => {
    setEvents((prev) => prev.filter((e) => e.localId !== localId));
  }, []);

  const dismissAll = useCallback(() => setEvents([]), []);

  useEffect(() => {
    if (typeof window === "undefined") return;
    cancelledRef.current = false;

    const apiUrl =
      options.url ??
      process.env.NEXT_PUBLIC_API_URL ??
      "http://127.0.0.1:8000";
    const wsUrl = options.url ?? wsUrlFromApi(apiUrl);
    const refreshOn = options.refreshOn ?? DEFAULT_REFRESH;
    const bufferSize = options.bufferSize ?? 5;

    const connect = () => {
      if (cancelledRef.current) return;
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        setConnected(true);
        backoffRef.current = 1000;
        // Heartbeat every 25s to keep proxies happy
        heartbeatRef.current = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) ws.send("ping");
        }, 25_000);
      };

      ws.onmessage = (e) => {
        let parsed: { type?: string; channel?: LiveEventChannel; data?: Record<string, unknown> };
        try {
          parsed = JSON.parse(e.data);
        } catch {
          return;
        }
        if (parsed.type !== "event" || !parsed.channel) return;
        const ev: LiveEvent = {
          localId: `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`,
          channel: parsed.channel,
          data: parsed.data ?? {},
          receivedAt: Date.now(),
        };
        setEvents((prev) => [ev, ...prev].slice(0, bufferSize));
        if (refreshOn.includes(ev.channel)) {
          router.refresh();
        }
      };

      ws.onclose = () => {
        setConnected(false);
        if (heartbeatRef.current) {
          clearInterval(heartbeatRef.current);
          heartbeatRef.current = null;
        }
        if (cancelledRef.current) return;
        const delay = Math.min(backoffRef.current, 16_000);
        backoffRef.current = Math.min(backoffRef.current * 2, 16_000);
        setTimeout(connect, delay);
      };

      ws.onerror = () => {
        // onclose will fire after onerror — handle reconnect there.
        ws.close();
      };
    };

    connect();

    return () => {
      cancelledRef.current = true;
      if (heartbeatRef.current) clearInterval(heartbeatRef.current);
      wsRef.current?.close();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return { events, connected, dismiss, dismissAll };
}
