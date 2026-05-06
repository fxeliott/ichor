/**
 * Ichor API client — fetch utilities for Server Components AND client.
 *
 * Strategy :
 *   - Server-side : direct hit to NEXT_PUBLIC_API_URL (or 127.0.0.1:8000
 *     fallback) — fast, in-process, no proxy hop.
 *   - Client-side : empty origin → same-origin call → Next.js rewrites
 *     in next.config.ts proxy /v1/* to the API. This makes the public
 *     tunnel the only public surface ; the API stays bound to localhost.
 */

const DEFAULT_REVALIDATE = 30; // seconds

const apiUrl = (): string => {
  // Browser : use same-origin so Next.js rewrites can proxy to the API.
  if (typeof window !== "undefined") {
    return "";
  }
  // SSR : direct call to the local API (fast, no proxy).
  return process.env["NEXT_PUBLIC_API_URL"] ?? "http://127.0.0.1:8000";
};

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

export type BriefingType = "pre_londres" | "pre_ny" | "ny_mid" | "ny_close" | "weekly" | "crisis";

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

export const listBriefings = (params: ListBriefingsParams = {}): Promise<BriefingList> => {
  const q = new URLSearchParams();
  if (params.limit) q.set("limit", String(params.limit));
  if (params.offset) q.set("offset", String(params.offset));
  if (params.briefingType) q.set("briefing_type", params.briefingType);
  if (params.asset) q.set("asset", params.asset);
  const qs = q.toString();
  return get<BriefingList>(`/v1/briefings${qs ? `?${qs}` : ""}`);
};

export const getBriefing = (id: string): Promise<Briefing> => get<Briefing>(`/v1/briefings/${id}`);

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
  limit = 100,
): Promise<BiasSignal[]> =>
  get<BiasSignal[]>(
    `/v1/bias-signals/history?asset=${encodeURIComponent(asset)}&horizon_hours=${horizonHours}&limit=${limit}`,
  );

export type NewsSourceKind = "news" | "central_bank" | "regulator" | "social" | "academic";

export type NewsTone = "positive" | "neutral" | "negative";

export interface NewsItem {
  id: string;
  fetched_at: string;
  source: string;
  source_kind: NewsSourceKind;
  title: string;
  summary: string | null;
  url: string;
  published_at: string;
  tone_label: NewsTone | null;
  tone_score: number | null;
}

export interface ListNewsParams {
  sourceKind?: NewsSourceKind;
  source?: string;
  tone?: NewsTone;
  sinceMinutes?: number;
  limit?: number;
}

export const listNews = (params: ListNewsParams = {}): Promise<NewsItem[]> => {
  const q = new URLSearchParams();
  if (params.sourceKind) q.set("source_kind", params.sourceKind);
  if (params.source) q.set("source", params.source);
  if (params.tone) q.set("tone", params.tone);
  if (params.sinceMinutes) q.set("since_minutes", String(params.sinceMinutes));
  if (params.limit) q.set("limit", String(params.limit));
  const qs = q.toString();
  return get<NewsItem[]>(`/v1/news${qs ? `?${qs}` : ""}`, 60);
};

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

export const signedCredibleInterval = (s: BiasSignal): { low: number; high: number } => {
  const sign = s.direction === "short" ? -1 : 1;
  const lo = (s.credible_interval_low - 0.5) * 2 * sign;
  const hi = (s.credible_interval_high - 0.5) * 2 * sign;
  return sign > 0 ? { low: lo, high: hi } : { low: hi, high: lo };
};

// ─────────────────────────── market data ───────────────────────────

export interface MarketBar {
  bar_date: string;
  asset: string;
  source: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number | null;
}

export const assetMarketHistory = (asset: string, days = 180): Promise<MarketBar[]> =>
  get<MarketBar[]>(`/v1/market/${encodeURIComponent(asset)}?days=${days}`, 60);

// ─────────────────────────── predictions ───────────────────────────

export interface PredictionRow {
  id: string;
  generated_at: string;
  model_id: string;
  model_family: string;
  asset: string;
  horizon_hours: number;
  direction: "long" | "short" | "neutral";
  raw_score: number;
  calibrated_probability: number | null;
  realized_direction: string | null;
  brier_contribution: number | null;
}

export interface ModelSummary {
  model_id: string;
  n_predictions: number;
  earliest: string | null;
  latest: string | null;
  asset: string | null;
  avg_brier: number | null;
}

export interface ListPredictionsParams {
  asset?: string;
  modelId?: string;
  sinceDays?: number;
  limit?: number;
}

export const listPredictions = (params: ListPredictionsParams = {}): Promise<PredictionRow[]> => {
  const q = new URLSearchParams();
  if (params.asset) q.set("asset", params.asset);
  if (params.modelId) q.set("model_id", params.modelId);
  if (params.sinceDays) q.set("since_days", String(params.sinceDays));
  if (params.limit) q.set("limit", String(params.limit));
  const qs = q.toString();
  return get<PredictionRow[]>(`/v1/predictions${qs ? `?${qs}` : ""}`, 60);
};

export const listModels = (): Promise<ModelSummary[]> =>
  get<ModelSummary[]>(`/v1/predictions/models`, 60);

// ─────────────────────────── sessions (Phase 1) ───────────────────────────

export type SessionType = "pre_londres" | "pre_ny" | "event_driven";
export type BiasDirection = "long" | "short" | "neutral";
export type CriticVerdict = "approved" | "amendments" | "blocked";
export type RegimeQuadrant = "haven_bid" | "funding_stress" | "goldilocks" | "usd_complacency";

export interface SessionCard {
  id: string;
  generated_at: string;
  session_type: SessionType;
  asset: string;
  model_id: string;
  regime_quadrant: RegimeQuadrant | null;
  bias_direction: BiasDirection;
  conviction_pct: number;
  magnitude_pips_low: number | null;
  magnitude_pips_high: number | null;
  timing_window_start: string | null;
  timing_window_end: string | null;
  mechanisms: { claim?: string; sources?: string[] }[] | null;
  invalidations: { condition?: string; threshold?: string | number; source?: string }[] | null;
  catalysts: { time?: string; event?: string; expected_impact?: string }[] | null;
  correlations_snapshot: Record<string, number> | null;
  polymarket_overlay:
    | {
        market?: string;
        yes_price?: number;
        divergence_vs_consensus?: number;
      }[]
    | null;
  source_pool_hash: string;
  critic_verdict: CriticVerdict | null;
  critic_findings: { sentence?: string; reason?: string; severity?: string }[] | null;
  claude_duration_ms: number | null;
  realized_close_session: number | null;
  realized_at: string | null;
  brier_contribution: number | null;
  created_at: string;
}

export interface SessionCardList {
  total: number;
  items: SessionCard[];
}

export const listLatestSessions = (
  sessionType?: SessionType,
  limit = 8,
): Promise<SessionCardList> => {
  const q = new URLSearchParams();
  if (sessionType) q.set("session_type", sessionType);
  q.set("limit", String(limit));
  return get<SessionCardList>(`/v1/sessions?${q.toString()}`, 30);
};

export const listSessionsForAsset = (asset: string, limit = 20): Promise<SessionCardList> =>
  get<SessionCardList>(`/v1/sessions/${encodeURIComponent(asset)}?limit=${limit}`, 30);

// ─────────────────────────── calibration (Phase 1) ───────────────────────────

export interface ReliabilityBin {
  bin_lower: number;
  bin_upper: number;
  count: number;
  mean_predicted: number;
  mean_realized: number;
}

export interface Calibration {
  n_cards: number;
  mean_brier: number;
  skill_vs_naive: number;
  hits: number;
  misses: number;
  window_days: number;
  asset: string | null;
  session_type: SessionType | null;
  regime_quadrant: RegimeQuadrant | null;
  reliability: ReliabilityBin[];
}

export interface CalibrationGroup {
  group_key: string;
  summary: Calibration;
}

export interface CalibrationGroups {
  groups: CalibrationGroup[];
}

export interface CalibrationParams {
  asset?: string;
  sessionType?: SessionType;
  regimeQuadrant?: RegimeQuadrant;
  windowDays?: number;
}

export const getCalibrationOverall = (params: CalibrationParams = {}): Promise<Calibration> => {
  const q = new URLSearchParams();
  if (params.asset) q.set("asset", params.asset);
  if (params.sessionType) q.set("session_type", params.sessionType);
  if (params.regimeQuadrant) q.set("regime_quadrant", params.regimeQuadrant);
  if (params.windowDays) q.set("window_days", String(params.windowDays));
  const qs = q.toString();
  return get<Calibration>(`/v1/calibration${qs ? `?${qs}` : ""}`, 300);
};

export const getCalibrationByAsset = (windowDays = 90): Promise<CalibrationGroups> =>
  get<CalibrationGroups>(`/v1/calibration/by-asset?window_days=${windowDays}`, 300);

export const getCalibrationByRegime = (windowDays = 90): Promise<CalibrationGroups> =>
  get<CalibrationGroups>(`/v1/calibration/by-regime?window_days=${windowDays}`, 300);

// ─────────────────────────── Intraday bars (Polygon) ───────────────────────────

export interface IntradayBar {
  time: number; // epoch seconds (UTC)
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number | null;
}

export const getIntradayBars = (asset: string, hours = 8): Promise<IntradayBar[]> =>
  get<IntradayBar[]>(`/v1/market/intraday/${encodeURIComponent(asset)}?hours=${hours}`, 30);

// ────────────────── data pool (debug + scenarios) ──────────────────

export interface DataPoolResponse {
  asset: string;
  generated_at: string;
  markdown_chars: number;
  sections_emitted: string[];
  sources_count: number;
  sources: string[];
  markdown: string;
}

export const getDataPool = (
  asset: string,
  opts?: {
    session_type?: "pre_londres" | "pre_ny" | "ny_mid" | "ny_close" | "event_driven";
    regime?: "haven_bid" | "funding_stress" | "goldilocks" | "usd_complacency";
    conviction_pct?: number;
  },
): Promise<DataPoolResponse> => {
  const qs = new URLSearchParams();
  if (opts?.session_type) qs.set("session_type", opts.session_type);
  if (opts?.regime) qs.set("regime", opts.regime);
  if (opts?.conviction_pct != null) qs.set("conviction_pct", String(opts.conviction_pct));
  const suffix = qs.toString() ? `?${qs.toString()}` : "";
  return get<DataPoolResponse>(`/v1/data-pool/${encodeURIComponent(asset)}${suffix}`, 30);
};

// ─────────────────── trade plan (RR analysis) ────────────────────

export type Bias = "long" | "short" | "neutral";

export interface TradePlan {
  asset: string;
  spot: number | null;
  bias: Bias;
  conviction_pct: number;
  magnitude_pips_low: number | null;
  magnitude_pips_high: number | null;

  entry_zone_low: number | null;
  entry_zone_high: number | null;
  stop_loss: number | null;
  tp1: number | null;
  tp3: number | null;
  tp_extended: number | null;
  risk_pips: number | null;
  reward_pips_tp3: number | null;
  rr_target: number;

  notes: string;
  markdown: string;
  sources: string[];
  derived_from: Record<string, string | null> | null;
}

export const getTradePlan = (asset: string, rrTarget = 3.0): Promise<TradePlan> =>
  get<TradePlan>(`/v1/trade-plan/${encodeURIComponent(asset)}?rr_target=${rrTarget}`, 30);

// ─────────────────── confluence engine ────────────────────

export interface ConfluenceDriver {
  factor: string;
  contribution: number;
  evidence: string;
  source: string | null;
}

export interface Confluence {
  asset: string;
  score_long: number;
  score_short: number;
  score_neutral: number;
  dominant_direction: Bias;
  confluence_count: number;
  drivers: ConfluenceDriver[];
  rationale: string;
}

export const getConfluence = (asset: string): Promise<Confluence> =>
  get<Confluence>(`/v1/confluence/${encodeURIComponent(asset)}`, 30);

export interface ConfluenceHistoryPoint {
  captured_at: string;
  score_long: number;
  score_short: number;
  score_neutral: number;
  dominant_direction: Bias;
  confluence_count: number;
}

export interface ConfluenceHistory {
  asset: string;
  window_days: number;
  n_points: number;
  points: ConfluenceHistoryPoint[];
}

export const getConfluenceHistory = (asset: string, windowDays = 30): Promise<ConfluenceHistory> =>
  get<ConfluenceHistory>(
    `/v1/confluence/${encodeURIComponent(asset)}/history?window_days=${windowDays}`,
    300,
  );

// ─────────────────── currency strength ────────────────────

export interface CurrencyStrengthEntry {
  currency: string;
  score: number;
  rank: number;
  n_pairs_contributing: number;
  contributions: [string, number][];
}

export interface CurrencyStrength {
  window_hours: number;
  generated_at: string;
  entries: CurrencyStrengthEntry[];
}

export const getCurrencyStrength = (windowHours = 24): Promise<CurrencyStrength> =>
  get<CurrencyStrength>(`/v1/currency-strength?window_hours=${windowHours}`, 30);

// ─────────────────── economic calendar ────────────────────

export interface CalendarEvent {
  when: string;
  when_time_utc: string | null;
  region: string;
  label: string;
  impact: "high" | "medium" | "low";
  affected_assets: string[];
  note: string;
  source: string | null;
}

export interface CalendarUpcoming {
  generated_at: string;
  horizon_days: number;
  events: CalendarEvent[];
}

export const getUpcomingCalendar = (
  opts: { horizonDays?: number; asset?: string } = {},
): Promise<CalendarUpcoming> => {
  const qs = new URLSearchParams();
  if (opts.horizonDays != null) qs.set("horizon_days", String(opts.horizonDays));
  if (opts.asset) qs.set("asset", opts.asset);
  const suffix = qs.toString() ? `?${qs.toString()}` : "";
  return get<CalendarUpcoming>(`/v1/calendar/upcoming${suffix}`, 60);
};

// ─────────────── cross-asset correlations ────────────────

export interface CorrelationMatrix {
  window_days: number;
  assets: string[];
  matrix: (number | null)[][];
  n_returns_used: number;
  generated_at: string;
  flags: string[];
}

export const getCorrelations = (windowDays = 30): Promise<CorrelationMatrix> =>
  get<CorrelationMatrix>(`/v1/correlations?window_days=${windowDays}`, 60);

// ─────────────── hourly volatility heatmap ────────────────

export interface HourlyVolEntry {
  hour_utc: number;
  median_bp: number;
  p75_bp: number;
  n_samples: number;
}

export interface HourlyVolReport {
  asset: string;
  window_days: number;
  entries: HourlyVolEntry[];
  best_hour_utc: number | null;
  worst_hour_utc: number | null;
  london_session_avg_bp: number | null;
  asian_session_avg_bp: number | null;
  generated_at: string;
}

export const getHourlyVol = (asset: string, windowDays = 30): Promise<HourlyVolReport> =>
  get<HourlyVolReport>(
    `/v1/hourly-volatility/${encodeURIComponent(asset)}?window_days=${windowDays}`,
    60,
  );

// ─────────────── brier feedback (auto-introspection) ────────────────

export interface BrierGroupStat {
  key: string;
  n: number;
  avg_brier: number;
  win_rate: number | null;
}

export interface BrierFeedback {
  n_cards_reconciled: number;
  window_days: number;
  overall_avg_brier: number | null;
  by_asset: BrierGroupStat[];
  by_session_type: BrierGroupStat[];
  by_regime: BrierGroupStat[];
  high_conviction_win_rate: number | null;
  low_conviction_win_rate: number | null;
  flags: string[];
  generated_at: string;
}

export const getBrierFeedback = (windowDays = 30): Promise<BrierFeedback> =>
  get<BrierFeedback>(`/v1/brier-feedback?window_days=${windowDays}`, 60);

// ─────────────── macro pulse (bundled snapshot) ────────────────

export interface VixTermPulse {
  vix_1m: number | null;
  vix_3m: number | null;
  ratio: number | null;
  spread: number | null;
  regime: string;
  interpretation: string;
}

export interface RiskComponent {
  name: string;
  series_id: string;
  value: number | null;
  contribution: number;
  rationale: string;
}

export interface RiskAppetitePulse {
  composite: number;
  band: string;
  components: RiskComponent[];
}

export interface YieldPoint {
  label: string;
  tenor_years: number;
  yield_pct: number | null;
}

export interface YieldCurvePulse {
  points: YieldPoint[];
  slope_3m_10y: number | null;
  slope_2y_10y: number | null;
  slope_5y_30y: number | null;
  real_yield_10y: number | null;
  inverted_segments: number;
  shape: string;
  note: string;
}

export interface FundingStressPulse {
  sofr: number | null;
  iorb: number | null;
  sofr_iorb_spread: number | null;
  sofr_effr_spread: number | null;
  rrp_usage: number | null;
  hy_oas: number | null;
  stress_score: number;
}

export interface SurpriseSeries {
  series_id: string;
  label: string;
  last_value: number | null;
  z_score: number | null;
}

export interface SurprisePulse {
  region: string;
  composite: number | null;
  band: string;
  series: SurpriseSeries[];
}

export interface MacroPulse {
  generated_at: string;
  vix_term: VixTermPulse;
  risk_appetite: RiskAppetitePulse;
  yield_curve: YieldCurvePulse;
  funding_stress: FundingStressPulse;
  surprise_index: SurprisePulse;
}

export const getMacroPulse = (): Promise<MacroPulse> => get<MacroPulse>(`/v1/macro-pulse`, 60);

// ─────────────── polymarket impact ────────────────

export interface PolymarketMarketHit {
  slug: string;
  question: string;
  yes: number;
  weight: number;
}

export interface PolymarketThemeHit {
  theme_key: string;
  label: string;
  n_markets: number;
  avg_yes: number;
  markets: PolymarketMarketHit[];
  impact_per_asset: Record<string, number>;
}

export interface PolymarketImpact {
  generated_at: string;
  n_markets_scanned: number;
  themes: PolymarketThemeHit[];
  asset_aggregate: Record<string, number>;
}

export const getPolymarketImpact = (hours = 24): Promise<PolymarketImpact> =>
  get<PolymarketImpact>(`/v1/polymarket-impact?hours=${hours}`, 60);
