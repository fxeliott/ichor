// Typed fetch wrapper for FastAPI backend (apps/api).
//
// Server-component-first: `fetch()` is called during SSR. If the API is
// unreachable, calls return `null` so the page can fall back to a mock
// (visible "API offline" indicator) instead of crashing the SSR.
//
// Reads `ICHOR_API_URL` (server-only env), defaults to localhost in dev.

const API_BASE = process.env.ICHOR_API_URL ?? "http://localhost:8001";

export interface ApiFetchOptions {
  /** Cache behavior. Default `no-store` (always fresh). */
  cache?: RequestCache;
  /** Next ISR revalidate seconds. Mutually exclusive with `cache`. */
  revalidate?: number;
  /** Override base URL (for tests). */
  baseUrl?: string;
}

/** GET request returning typed JSON or `null` on any failure. */
export async function apiGet<T>(path: string, opts: ApiFetchOptions = {}): Promise<T | null> {
  const base = opts.baseUrl ?? API_BASE;
  const url = path.startsWith("http") ? path : `${base}${path}`;

  const fetchInit: RequestInit & { next?: { revalidate?: number } } = {};
  if (opts.revalidate !== undefined) {
    fetchInit.next = { revalidate: opts.revalidate };
  } else {
    fetchInit.cache = opts.cache ?? "no-store";
  }

  try {
    const res = await fetch(url, fetchInit);
    if (!res.ok) {
      console.warn(`[api] ${url} → ${res.status} ${res.statusText}`);
      return null;
    }
    return (await res.json()) as T;
  } catch (err) {
    console.warn(`[api] ${url} → network error: ${err instanceof Error ? err.message : err}`);
    return null;
  }
}

/**
 * POST/PUT/DELETE wrapper. Returns the parsed response body on 2xx,
 * `null` on any error. Caller is responsible for picking the right
 * `method`. Used by mutation client components (e.g. /journal).
 *
 * NB: client-side fetch — this hits the SAME-origin proxy (Next route
 * `/api/[...path]/proxy`) when called from the browser, NOT the
 * Hetzner backend directly (CORS would block it). When called from a
 * Server Action it goes straight to API_BASE.
 */
export async function apiMutate<TRes, TBody = unknown>(
  path: string,
  body: TBody,
  opts: { method?: "POST" | "PUT" | "PATCH" | "DELETE"; baseUrl?: string } = {},
): Promise<TRes | null> {
  // Client-side calls go through the same-origin proxy (next.config
  // rewrites /v1/*). Server-side calls use API_BASE directly.
  const isBrowser = typeof window !== "undefined";
  const base = opts.baseUrl ?? (isBrowser ? "" : API_BASE);
  const url = path.startsWith("http") ? path : `${base}${path}`;
  const method = opts.method ?? "POST";

  try {
    const res = await fetch(url, {
      method,
      headers: { "Content-Type": "application/json" },
      body: method === "DELETE" ? null : JSON.stringify(body),
      cache: "no-store",
    });
    if (!res.ok) {
      console.warn(`[api] ${method} ${url} → ${res.status} ${res.statusText}`);
      return null;
    }
    if (res.status === 204) return null; // No Content
    return (await res.json()) as TRes;
  } catch (err) {
    console.warn(
      `[api] ${method} ${url} → network error: ${err instanceof Error ? err.message : err}`,
    );
    return null;
  }
}

// ─────────────────────── Response shapes (subset) ───────────────────────
// Mirrors apps/api/src/ichor_api/schemas.py.
// Keep narrow: only fields actually consumed by frontend pages.

export interface TradePlanSchema {
  entry_low: number;
  entry_high: number;
  invalidation_level: number;
  invalidation_condition: string;
  tp_rr3: number;
  tp_rr15: number | null;
  partial_scheme: string;
}

export interface ConfluenceDriverSchema {
  factor: string;
  /** Signed in [-1, +1] — positive = supports the bias_direction. */
  contribution: number;
}

export interface IdeaSetSchema {
  top: string;
  supporting: string[];
  risks: string[];
}

export interface CalibrationStatSchema {
  brier: number;
  sample_size: number;
  trend: "bull" | "bear" | "neutral";
}

export interface SessionCard {
  id: string;
  generated_at: string;
  session_type: "pre_londres" | "pre_ny" | "event_driven";
  asset: string;
  model_id: string;
  regime_quadrant: string | null;
  bias_direction: "long" | "short" | "neutral";
  conviction_pct: number;
  magnitude_pips_low: number | null;
  magnitude_pips_high: number | null;
  timing_window_start: string | null;
  timing_window_end: string | null;
  mechanisms: unknown;
  invalidations: unknown;
  catalysts: unknown;
  correlations_snapshot: unknown;
  polymarket_overlay: unknown;
  source_pool_hash: string;
  critic_verdict: string | null;
  critic_findings: unknown;
  claude_duration_ms: number | null;
  realized_close_session: number | null;
  realized_at: string | null;
  brier_contribution: number | null;
  created_at: string;

  // Phase 2 typed enrichment — populated when claude_raw_response exposes
  // the structured sub-objects ; null otherwise.
  thesis: string | null;
  trade_plan: TradePlanSchema | null;
  ideas: IdeaSetSchema | null;
  confluence_drivers: ConfluenceDriverSchema[] | null;
  calibration: CalibrationStatSchema | null;
}

export interface SessionCardList {
  total: number;
  items: SessionCard[];
}

export interface Briefing {
  id: string;
  briefing_type: string;
  triggered_at: string;
  assets: string[];
  status: string;
  briefing_markdown: string | null;
  claude_duration_ms: number | null;
  audio_mp3_url: string | null;
  created_at: string;
}

export interface BriefingList {
  total: number;
  items: Briefing[];
}

export interface AdminTableCount {
  table: string;
  rows: number;
  most_recent_at: string | null;
}

export interface AdminCardStat {
  asset: string;
  n_total: number;
  n_approved: number;
  n_amendments: number;
  n_blocked: number;
  avg_duration_ms: number;
  avg_conviction_pct: number;
  last_at: string | null;
}

export interface AdminStatus {
  generated_at: string;
  tables: AdminTableCount[];
  cards: AdminCardStat[];
  n_cards_24h: number;
  n_cards_total: number;
  last_card_at: string | null;
  claude_runner_url: string | null;
}

export interface PostMortemSummary {
  id: string;
  iso_year: number;
  iso_week: number;
  generated_at: string;
  markdown_path: string;
  n_top_hits: number;
  n_top_miss: number;
  n_drift_flags: number;
  brier_30d: number | null;
  actionable_count: number;
  actionable_resolved: number;
}

export interface PostMortemList {
  total: number;
  items: PostMortemSummary[];
}

export interface ReliabilityBin {
  bin_lower: number;
  bin_upper: number;
  count: number;
  mean_predicted: number;
  mean_realized: number;
}

export interface CalibrationSummary {
  n_cards: number;
  mean_brier: number;
  skill_vs_naive: number;
  hits: number;
  misses: number;
  window_days: number;
  asset: string | null;
  session_type: string | null;
  regime_quadrant: string | null;
  reliability: ReliabilityBin[];
}

export interface CalibrationGroup {
  group_key: string;
  summary: CalibrationSummary;
}

export interface CalibrationGroups {
  groups: CalibrationGroup[];
}

export interface PolymarketMarketHit {
  slug: string;
  question: string;
  yes: number;
  weight: number;
}

export interface PolymarketTheme {
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
  themes: PolymarketTheme[];
  asset_aggregate: Record<string, number>;
}

export interface DivergenceAlertItem {
  question: string;
  gap: number;
  high_venue: string;
  high_price: number;
  low_venue: string;
  low_price: number;
  similarity: number;
  by_venue: Record<string, Record<string, unknown>>;
}

export interface DivergenceList {
  since_hours: number;
  match_threshold: number;
  gap_threshold: number;
  n_alerts: number;
  alerts: DivergenceAlertItem[];
}

export interface VixTerm {
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

export interface RiskAppetite {
  composite: number;
  band: string;
  components: RiskComponent[];
}

export interface YieldPoint {
  label: string;
  tenor_years: number;
  yield_pct: number | null;
}

export interface YieldCurve {
  points: YieldPoint[];
  slope_3m_10y: number | null;
  slope_2y_10y: number | null;
  slope_5y_30y: number | null;
  real_yield_10y: number | null;
  inverted_segments: number;
  shape: string;
  note: string;
}

/** Standalone /v1/yield-curve response (richer than the embedded variant
 *  used inside MacroPulse — adds series_id + observation_date per tenor
 *  and a `sources` list for the disclosure footer). */
export interface YieldTenorPoint {
  label: string;
  tenor_years: number;
  series_id: string;
  yield_pct: number | null;
  observation_date: string | null;
}

export interface YieldCurveStandalone {
  points: YieldTenorPoint[];
  slope_3m_10y: number | null;
  slope_2y_10y: number | null;
  slope_5y_30y: number | null;
  real_yield_10y: number | null;
  inverted_segments: number;
  shape: string;
  note: string;
  sources: string[];
}

export interface FundingStress {
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

export interface SurpriseIndex {
  region: string;
  composite: number | null;
  band: string;
  series: SurpriseSeries[];
}

export interface MacroPulse {
  generated_at: string;
  vix_term: VixTerm;
  risk_appetite: RiskAppetite;
  yield_curve: YieldCurve;
  funding_stress: FundingStress;
  surprise_index: SurpriseIndex;
}

export interface GraphNode {
  id: string;
  label: string;
  kind?: string;
  weight?: number;
  [k: string]: unknown;
}

export interface GraphEdge {
  source: string;
  target: string;
  weight?: number;
  kind?: string;
  [k: string]: unknown;
}

export interface GraphPayload {
  generated_at?: string;
  nodes: GraphNode[];
  edges: GraphEdge[];
  [k: string]: unknown;
}

export interface CalendarEvent {
  when: string; // YYYY-MM-DD
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

export interface AlertItem {
  id: string;
  alert_code: string;
  severity: "info" | "warning" | "critical";
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

export interface NewsItem {
  id: string;
  fetched_at: string;
  source: string;
  source_kind: string;
  title: string;
  summary: string | null;
  url: string;
  published_at: string;
  tone_label: string | null;
  tone_score: number | null;
}

export interface CorrelationMatrix {
  window_days: number;
  assets: string[];
  matrix: (number | null)[][];
  n_returns_used: number;
  generated_at: string;
  flags: string[];
}

export interface NarrativeTopic {
  keyword: string;
  count: number;
  share: number;
  sample_title: string | null;
}

export interface NarrativeReport {
  window_hours: number;
  n_documents: number;
  n_tokens: number;
  topics: NarrativeTopic[];
}

export interface CountryHotspot {
  country: string;
  count: number;
  mean_tone: number;
  most_negative_title: string | null;
}

export interface GeopoliticsHeatmap {
  window_hours: number;
  n_events: number;
  countries: CountryHotspot[];
}

export interface ScenarioRow {
  kind: "continuation" | "reversal" | "sideways";
  probability: number;
  triggers: string[];
}

export interface ScenariosLevels {
  spot: number | null;
  pdh: number | null;
  pdl: number | null;
  asian_high: number | null;
  asian_low: number | null;
}

export interface EconomicEventOut {
  id: string;
  currency: string;
  scheduled_at: string | null;
  is_all_day: boolean;
  title: string;
  impact: "low" | "medium" | "high" | "holiday";
  forecast: string | null;
  previous: string | null;
  url: string | null;
  source: string;
  fetched_at: string;
}

export interface EconomicEventListOut {
  generated_at: string;
  window_back_minutes: number;
  window_forward_minutes: number;
  n_events: number;
  events: EconomicEventOut[];
}

export interface TodayMacroSummary {
  risk_composite: number;
  risk_band: string;
  funding_stress: number;
  vix_regime: string;
  vix_1m: number | null;
}

export interface TodayCalendarEvent {
  when: string;
  when_time_utc: string | null;
  region: string;
  label: string;
  impact: "high" | "medium" | "low";
  affected_assets: string[];
  note: string;
  source: string | null;
}

export interface TodaySessionPreview {
  asset: string;
  bias_direction: "long" | "short" | "neutral";
  conviction_pct: number;
  magnitude_pips_low: number | null;
  magnitude_pips_high: number | null;
  regime_quadrant: string | null;
  generated_at: string;
  thesis: string | null;
  trade_plan: TradePlanSchema | null;
  ideas: IdeaSetSchema | null;
  confluence_drivers: ConfluenceDriverSchema[] | null;
}

export interface TodaySnapshotOut {
  generated_at: string;
  macro: TodayMacroSummary;
  calendar_window_days: number;
  n_calendar_events: number;
  calendar_events: TodayCalendarEvent[];
  n_session_cards: number;
  top_sessions: TodaySessionPreview[];
}

export interface ScenariosResponse {
  asset: string;
  session_type: "pre_londres" | "pre_ny" | "ny_mid" | "ny_close" | "event_driven";
  regime: "haven_bid" | "funding_stress" | "goldilocks" | "usd_complacency" | null;
  conviction_pct: number;
  sources: ("latest_session_card" | "caller_default")[];
  generated_at: string;
  rationale: string;
  levels: ScenariosLevels;
  scenarios: ScenarioRow[];
  notes: string[];
  latest_card_id: string | null;
}

// ─────────────────────── Cross-asset heatmap ───────────────────────

export interface HeatmapCell {
  sym: string;
  value: number | null;
  bias: "bull" | "bear" | "neutral";
  unit: string;
}

export interface HeatmapRow {
  row: string;
  cells: HeatmapCell[];
}

export interface CrossAssetHeatmap {
  generated_at: string;
  rows: HeatmapRow[];
  sources: string[];
}

// ─────────────────────── Pass 4 scenario tree ───────────────────────

export interface Pass4MagnitudeRange {
  low: number;
  high: number;
}

export interface Pass4Scenario {
  id: string; // s1..s7
  label: string;
  probability: number; // [0, 1]
  bias: "bull" | "bear" | "neutral";
  magnitude_pips: Pass4MagnitudeRange;
  primary_mechanism: string;
  invalidation: string;
  counterfactual_anchor: string | null;
}

export interface Pass4ScenarioTree {
  asset: string;
  generated_at: string;
  session_card_id: string | null;
  n_scenarios: number; // 0..7
  sum_probability: number;
  tail_padded: boolean;
  scenarios: Pass4Scenario[];
}

// ─────────────────────── Bias signals (legacy) ───────────────────────

export interface BiasSignalOut {
  id: string;
  generated_at: string;
  model_id: string;
  asset: string;
  horizon_hours: number;
  direction: "long" | "short" | "neutral";
  probability: number;
  credible_interval_low: number;
  credible_interval_high: number;
  weights_snapshot: Record<string, number>;
}

// ─────────────────────── Predictions ───────────────────────

export interface PredictionOut {
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

// ─────────────────────── Confluence ───────────────────────

export interface ConfluenceDriverOut {
  factor: string;
  contribution: number;
  evidence: string;
  source: string | null;
}

export interface ConfluenceOut {
  asset: string;
  score_long: number;
  score_short: number;
  score_neutral: number;
  dominant_direction: "long" | "short" | "neutral";
  confluence_count: number;
  drivers: ConfluenceDriverOut[];
  rationale: string;
}

export interface ConfluenceHistoryPoint {
  captured_at: string;
  score_long: number;
  score_short: number;
  score_neutral: number;
  dominant_direction: string;
  confluence_count: number;
}

export interface ConfluenceHistoryOut {
  asset: string;
  window_days: number;
  n_points: number;
  points: ConfluenceHistoryPoint[];
}

// ─────────────────────── Currency strength ───────────────────────

export interface StrengthEntry {
  currency: string;
  score: number;
  rank: number;
  n_pairs_contributing: number;
  contributions: [string, number][];
}

export interface StrengthOut {
  window_hours: number;
  generated_at: string;
  entries: StrengthEntry[];
}

// ─────────────────────── Hourly volatility ───────────────────────

export interface HourlyVolEntry {
  hour_utc: number;
  median_bp: number;
  p75_bp: number;
  n_samples: number;
}

export interface HourlyVolOut {
  asset: string;
  window_days: number;
  entries: HourlyVolEntry[];
  best_hour_utc: number | null;
  worst_hour_utc: number | null;
  london_session_avg_bp: number | null;
  asian_session_avg_bp: number | null;
  generated_at: string;
}

// ─────────────────────── Portfolio exposure ───────────────────────

export interface ExposureCardLite {
  asset: string;
  bias: string;
  conviction_pct: number;
  magnitude_pips_low: number | null;
  magnitude_pips_high: number | null;
  session_type: string;
  created_at: string;
}

export interface ExposureAxis {
  name: string;
  score: number;
  contributors: [string, number][];
}

export interface ExposureOut {
  n_cards: number;
  cards: ExposureCardLite[];
  axes: ExposureAxis[];
  concentration_warnings: string[];
  generated_at: string;
}

// ─────────────────────── Brier feedback ───────────────────────

export interface BrierGroupStat {
  key: string;
  n: number;
  avg_brier: number;
  win_rate: number | null;
}

export interface BrierFeedbackOut {
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

// ─────────────────────── Data pool ───────────────────────

export interface DataPoolOut {
  asset: string;
  generated_at: string;
  markdown_chars: number;
  sections_emitted: string[];
  sources_count: number;
  sources: string[];
  markdown: string;
}

// ─────────────────────── Counterfactual (Pass 5) ───────────────────────

export interface CounterfactualResponse {
  session_card_id: string;
  asset: string;
  original_generated_at: string;
  original_bias: string;
  original_conviction_pct: number;
  asked_at: string;
  scrubbed_event: string;
  counterfactual_bias: string;
  counterfactual_conviction_pct: number;
  delta_narrative: string;
  new_dominant_drivers: string[];
  confidence_delta: number;
}

// ─────────────────────── Trade plan ───────────────────────

export interface TradePlanOut {
  asset: string;
  spot: number | null;
  bias: "long" | "short" | "neutral";
  conviction_pct: number;
  magnitude_pips_low: number | null;
  magnitude_pips_high: number | null;
  entry_zone_low: number | null;
  entry_zone_high: number | null;
  stop_loss: number | null;
  tp1: number | null;
  tp3: number | null;
}

// ─────────────────────── Market data ───────────────────────

export interface MarketBarOut {
  bar_date: string;
  asset: string;
  source: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number | null;
}

export interface IntradayBarOut {
  time: number; // epoch seconds (UTCTimestamp for lightweight-charts)
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number | null;
}

// ─────────────────────── Sources catalog ───────────────────────

export type SourceStatus = "live" | "stale" | "down";
export type SourceCategory = "macro" | "fx" | "options" | "sentiment" | "geopolitics" | "structure";
export type SourceCadence = "intraday" | "hourly" | "daily" | "weekly";

export interface SourceOut {
  id: string;
  name: string;
  category: SourceCategory;
  cadence: SourceCadence;
  status: SourceStatus;
  last_fetch_at: string | null;
  rows_24h: number;
  cost_per_month: string;
  api_key_required: boolean;
}

export interface SourcesListOut {
  generated_at: string;
  n_sources: number;
  n_live: number;
  n_stale: number;
  n_down: number;
  monthly_cost_total_usd: number;
  sources: SourceOut[];
}

// ─────────────────────── Helpers ───────────────────────

/** True when the API responded successfully. Used by pages to choose
 *  between live data and the mock-fallback rendering. */
export function isLive<T>(data: T | null): data is T {
  return data !== null;
}
