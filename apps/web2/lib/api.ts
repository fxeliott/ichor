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

// r62 (ADR-083 D3) — KeyLevel snapshot persisted into session_card_audit.
// Mirror of `apps/api/src/ichor_api/routers/key_levels.py:KeyLevelOut`.
export type KeyLevelKind =
  | "tga_liquidity_gate"
  | "rrp_liquidity_gate"
  | "gamma_flip"
  | "gex_call_wall"
  | "gex_put_wall"
  | "peg_break_hkma"
  | "peg_break_pboc_fix"
  | "vix_regime_switch"
  | "skew_regime_switch"
  | "hy_oas_percentile"
  | "polymarket_decision";

export interface KeyLevel {
  asset: string;
  level: number;
  kind: KeyLevelKind;
  side: string;
  source: string;
  note: string;
}

export interface KeyLevelsResponse {
  count: number;
  items: KeyLevel[];
}

// r68 — Pass-6 7-bucket scenario decomposition (ADR-085). Mirror of
// session_card_audit.scenarios JSONB. 7 canonical-ordered entries
// (crash_flush..melt_up), sum(p) == 1.0. The outcome-probability
// distribution = the "prendre plus ou moins de risque" answer.
export type ScenarioLabel =
  | "crash_flush"
  | "strong_bear"
  | "mild_bear"
  | "base"
  | "mild_bull"
  | "strong_bull"
  | "melt_up";

export interface Scenario {
  label: ScenarioLabel;
  /** Probability in [0, 0.95] ; the 7 entries sum to 1.0. */
  p: number;
  /** [low, high] pip move for this bucket (signed : negative = down). */
  magnitude_pips: [number, number];
  mechanism: string;
}

export interface SessionCard {
  id: string;
  generated_at: string;
  // Canonical 5-window contract — mirror of ichor_brain.types.SessionType
  // + apps/api schemas.py SessionCardOut (r66 fix : was 3-value, drifted
  // from the 4-windows/day backend design, 500'd /v1/sessions).
  session_type: "pre_londres" | "pre_ny" | "ny_mid" | "ny_close" | "event_driven";
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
  /** r62 (ADR-083 D3) — KeyLevel snapshot persisted at orchestrator
   *  finalization. Empty array `[]` is the canonical "all NORMAL" state. */
  key_levels: KeyLevel[];
  /** r68 — Pass-6 7-bucket scenario decomposition (ADR-085). `[]` for
   *  legacy / pre-Pass-6 cards. 7 entries sum(p)==1.0 when present. */
  scenarios: Scenario[];
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

/** r65 — fetch the live KeyLevels snapshot from `/v1/key-levels`. */
export async function getKeyLevels(): Promise<KeyLevelsResponse | null> {
  return apiGet<KeyLevelsResponse>("/v1/key-levels");
}

/** r68 — fetch the upcoming economic calendar from `/v1/calendar/upcoming`. */
export async function getCalendarUpcoming(): Promise<CalendarUpcoming | null> {
  return apiGet<CalendarUpcoming>("/v1/calendar/upcoming");
}

/** r69 — fetch recent news items from `/v1/news` (bare list, tone-scored). */
export async function getNews(limit = 12): Promise<NewsItem[] | null> {
  return apiGet<NewsItem[]>(`/v1/news?limit=${limit}`);
}

// r69 — MyFXBook retail positioning (contrarian sentiment). Mirror of
// apps/api routers/positioning.py PositioningOut. The W77 collector was
// LIVE since 2026-05-09 but had no read endpoint until r69.
export interface PositioningEntry {
  pair: string;
  long_pct: number;
  short_pct: number;
  long_volume: number | null;
  short_volume: number | null;
  long_positions: number | null;
  short_positions: number | null;
  fetched_at: string;
  dominant_side: "long" | "short" | "balanced";
  intensity: "balanced" | "crowded" | "extreme";
  contrarian_tilt: "bullish" | "bearish" | "neutral";
  note: string;
}

export interface PositioningOut {
  generated_at: string;
  n_pairs: number;
  entries: PositioningEntry[];
}

/** r69 — fetch MyFXBook retail positioning from `/v1/positioning`. */
export async function getPositioning(): Promise<PositioningOut | null> {
  return apiGet<PositioningOut>("/v1/positioning");
}

/**
 * r75 (ADR-099 Tier 1.1) — intraday OHLCV bars from
 * `/v1/market/intraday/{asset}` (reuses `IntradayBarOut`). The endpoint
 * caps `hours` at 72 and returns the whole window ASCENDING; `limit`
 * truncates from the OLDEST end (verified R59). So to reach the most
 * recent bar even on a weekend/holiday (markets closed → last data is
 * Friday) we request the full window and the caller slices the tail
 * server-side. `volume` is a Polygon tick/aggregate ACTIVITY proxy, not
 * real exchange volume (FX is decentralised — true volume does not exist).
 */
export async function getIntradayBars(
  asset: string,
  hours = 72,
  limit = 10000,
): Promise<IntradayBarOut[] | null> {
  return apiGet<IntradayBarOut[]>(
    `/v1/market/intraday/${encodeURIComponent(asset)}?hours=${hours}&limit=${limit}`,
  );
}

// r76 — geopolitics briefing (AI-GPR headline + negative GDELT). Mirror
// of apps/api routers/geopolitics.py GeopoliticsBriefingOut. `band` is a
// ratio to the published GPR baseline (100 = 1985-2019 mean), NOT a
// fabricated threshold ; `as_of_days` surfaces GPR source lag honestly.
export interface GprReading {
  value: number;
  observation_date: string;
  as_of_days: number;
  band: "bas" | "normal" | "élevé" | "très élevé";
  baseline: number;
}

export interface GdeltNegative {
  tone: number;
  title: string;
  domain: string | null;
  query_label: string | null;
  url: string | null;
}

export interface GeopoliticsBriefing {
  gpr: GprReading | null;
  gdelt_window_hours: number;
  n_events_window: number;
  gdelt_negatives: GdeltNegative[];
}

/** r77 — fetch the geopolitics briefing from `/v1/geopolitics/briefing`. */
export async function getGeopoliticsBriefing(
  hours = 48,
  top = 6,
): Promise<GeopoliticsBriefing | null> {
  return apiGet<GeopoliticsBriefing>(`/v1/geopolitics/briefing?hours=${hours}&top=${top}`);
}

// r80 — CFTC institutional positioning ("acteurs du marché" / smart
// money, distinct from MyFXBook retail). Mirror of apps/api
// routers/positioning.py InstitutionalPositioningOut. Weekly cadence ;
// `report_date` makes the CFTC lag explicit. tff covers all 5 assets
// (incl. SPX500) ; cot covers 4 (null otherwise — honest, ADR-093).
export interface TffPositioning {
  market_code: string;
  report_date: string;
  open_interest: number;
  dealer_net: number;
  asset_mgr_net: number;
  lev_money_net: number;
  other_net: number;
  dealer_dw: number | null;
  asset_mgr_dw: number | null;
  lev_money_dw: number | null;
  smart_money_divergence: boolean;
}

export interface CotPositioning {
  market_code: string;
  report_date: string;
  open_interest: number;
  managed_money_net: number;
  swap_dealer_net: number;
  producer_net: number;
  delta_1w: number | null;
  delta_4w: number | null;
  delta_12w: number | null;
  pattern: "accelerating" | "reversal" | "stable";
}

export interface InstitutionalPositioning {
  asset: string;
  cadence: string;
  tff: TffPositioning | null;
  cot: CotPositioning | null;
}

/** r81 — fetch CFTC institutional positioning from `/v1/positioning/institutional`. */
export async function getInstitutionalPositioning(
  asset: string,
): Promise<InstitutionalPositioning | null> {
  return apiGet<InstitutionalPositioning>(
    `/v1/positioning/institutional?asset=${encodeURIComponent(asset)}`,
  );
}

/** r82 — live cross-asset correlation matrix from `/v1/correlations`
 *  (reuses CorrelationMatrix). Fallback source for the briefing
 *  Corrélations panel when `card.correlations_snapshot` is absent. */
export async function getCorrelations(windowDays = 30): Promise<CorrelationMatrix | null> {
  return apiGet<CorrelationMatrix>(`/v1/correlations?window_days=${windowDays}`);
}

// r78 — DST-correct market session + US-holiday signal. Mirror of
// apps/api routers/calendar.py SessionStatusOut. Consumed CLIENT-side by
// SessionStatus.tsx via the same-origin /v1 proxy (next.config rewrite) —
// it replaces the old DST-naive browser UTC heuristic. `next_open_paris`
// is an absolute ISO instant so the live countdown needs no local tz math.
export interface SessionStatusOut {
  now_paris: string;
  weekday: string;
  state:
    | "weekend"
    | "us_holiday"
    | "pre_londres"
    | "london_active"
    | "pre_ny"
    | "ny_active"
    | "off_hours";
  market_closed_fx: boolean;
  market_closed_us_equity: boolean;
  holiday_name: string | null;
  next_open_label: string;
  next_open_paris: string;
  minutes_until_next_open: number;
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

// W101 — Scoreboard multi-window matrix shapes mirror
// `apps/api/src/ichor_api/routers/calibration.py` ScoreboardOut /
// ScoreboardWindowOut / ScoreboardCellOut. Adding here for type-safe
// SSR fetch in `app/calibration/page.tsx` heatmap section.

export interface ScoreboardCell {
  asset: string;
  session_type: string;
  n_cards: number;
  mean_brier: number;
  skill_vs_naive: number;
  hits: number;
  misses: number;
}

export interface ScoreboardWindow {
  window_label: string; // "30d" | "90d" | "all"
  window_days: number;
  n_cells: number;
  cells: ScoreboardCell[];
}

export interface CalibrationScoreboard {
  generated_at: string; // ISO datetime
  windows: ScoreboardWindow[];
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
