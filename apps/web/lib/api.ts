/**
 * Ichor API client — server-side fetch utilities for Next.js Server Components.
 *
 * Reads `NEXT_PUBLIC_API_URL` (defaults to localhost during dev). All calls
 * use `next: { revalidate }` to participate in Next's request cache and
 * keep latency low while remaining fresh enough for a market dashboard.
 */

const DEFAULT_REVALIDATE = 30; // seconds

const apiUrl = (): string =>
  process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

async function get<T>(path: string, revalidate = DEFAULT_REVALIDATE): Promise<T> {
  const res = await fetch(`${apiUrl()}${path}`, {
    next: { revalidate },
    headers: { Accept: "application/json" },
  });
  if (!res.ok) {
    let detail = "";
    try {
      const j = (await res.json()) as { detail?: string };
      if (j.detail) detail = `: ${j.detail}`;
    } catch {
      // ignore parse errors — non-JSON error bodies happen
    }
    throw new ApiError(`API ${path} failed (${res.status})${detail}`, res.status);
  }
  return res.json() as Promise<T>;
}

// ─────────────────────────── shapes ───────────────────────────

export type BriefingType =
  | "pre_londres"
  | "pre_ny"
  | "ny_mid"
  | "ny_close"
  | "weekly"
  | "crisis";

export type BriefingStatus =
  | "pending"
  | "context_assembled"
  | "claude_running"
  | "completed"
  | "failed";

export interface Briefing {
  id: string;
  briefing_type: BriefingType;
  triggered_at: string;
  assets: string[];
  status: BriefingStatus;
  briefing_markdown: string | null;
  claude_duration_ms: number | null;
  audio_mp3_url: string | null;
  created_at: string;
}

export interface BriefingList {
  total: number;
  items: Briefing[];
}

export type AlertSeverity = "info" | "warning" | "critical";

export interface Alert {
  id: string;
  alert_code: string;
  severity: AlertSeverity;
  asset: string | null;
  triggered_at: string;
  metric_name: string;
  metric_value: number;
  threshold: number;
  direction: "above" | "below" | "cross_up" | "cross_down";
  title: string;
  description: string | null;
  acknowledged_at: string | null;
}

export interface BiasSignal {
  id: string;
  asset: string;
  horizon_hours: number;
  direction: "long" | "short" | "neutral";
  probability: number;
  credible_interval_low: number;
  credible_interval_high: number;
  contributing_predictions: string[];
  weights_snapshot: Record<string, number>;
  generated_at: string;
}

// ─────────────────────────── endpoints ───────────────────────────

export interface ListBriefingsParams {
  limit?: number;
  offset?: number;
  briefingType?: BriefingType;
  asset?: string;
}

export const listBriefings = (
  params: ListBriefingsParams = {}
): Promise<BriefingList> => {
  const q = new URLSearchParams();
  if (params.limit) q.set("limit", String(params.limit));
  if (params.offset) q.set("offset", String(params.offset));
  if (params.briefingType) q.set("briefing_type", params.briefingType);
  if (params.asset) q.set("asset", params.asset);
  const qs = q.toString();
  return get<BriefingList>(`/v1/briefings${qs ? `?${qs}` : ""}`);
};

export const getBriefing = (id: string): Promise<Briefing> =>
  get<Briefing>(`/v1/briefings/${id}`);

export interface ListAlertsParams {
  severity?: AlertSeverity;
  asset?: string;
  unacknowledgedOnly?: boolean;
  limit?: number;
}

export const listAlerts = (params: ListAlertsParams = {}): Promise<Alert[]> => {
  const q = new URLSearchParams();
  if (params.severity) q.set("severity", params.severity);
  if (params.asset) q.set("asset", params.asset);
  if (params.unacknowledgedOnly) q.set("unacknowledged_only", "true");
  if (params.limit) q.set("limit", String(params.limit));
  const qs = q.toString();
  return get<Alert[]>(`/v1/alerts${qs ? `?${qs}` : ""}`);
};

export const currentBiasSignals = (horizonHours = 24): Promise<BiasSignal[]> =>
  get<BiasSignal[]>(`/v1/bias-signals/current?horizon_hours=${horizonHours}`);

export const biasSignalHistory = (
  asset: string,
  horizonHours = 24,
  limit = 100
): Promise<BiasSignal[]> =>
  get<BiasSignal[]>(
    `/v1/bias-signals/history?asset=${encodeURIComponent(asset)}&horizon_hours=${horizonHours}&limit=${limit}`
  );

// ─────────────────────────── helpers for UI ───────────────────────────

/**
 * Convert a BiasSignal into the signed bias used by <BiasBar>.
 *
 *   bias = (probability - 0.5) * 2 * (direction === "long" ? 1 : -1)
 *
 * For neutral direction we still surface the deviation from 50% so the bar
 * shows how confident the aggregator is in the no-trade call.
 */
export const signedBias = (s: BiasSignal): number => {
  const sign = s.direction === "short" ? -1 : 1;
  return (s.probability - 0.5) * 2 * sign;
};

export const signedCredibleInterval = (
  s: BiasSignal
): { low: number; high: number } => {
  const sign = s.direction === "short" ? -1 : 1;
  const lo = (s.credible_interval_low - 0.5) * 2 * sign;
  const hi = (s.credible_interval_high - 0.5) * 2 * sign;
  return sign > 0 ? { low: lo, high: hi } : { low: hi, high: lo };
};
