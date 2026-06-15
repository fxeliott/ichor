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
  /** r140 — optional AbortSignal forwarded to fetch() so client-side
   *  pollers (FreshDataBanner) can actually cancel in-flight requests
   *  on unmount. Without this, AbortController in callers was a no-op
   *  (code-reviewer R2 — wired end-to-end, not decorative). */
  signal?: AbortSignal;
}

/** GET request returning typed JSON or `null` on any failure. */
export async function apiGet<T>(path: string, opts: ApiFetchOptions = {}): Promise<T | null> {
  // Client-side calls go through the same-origin proxy (next.config
  // rewrites /v1/*). Server-side (SSR/Server Action) calls use
  // API_BASE directly. Mirrors `apiMutate` — `ICHOR_API_URL` is a
  // server-only env, so a browser `API_BASE` would be the unreachable
  // localhost dev port and get CSP-blocked on the public deploy.
  const isBrowser = typeof window !== "undefined";
  const base = opts.baseUrl ?? (isBrowser ? "" : API_BASE);
  const url = path.startsWith("http") ? path : `${base}${path}`;

  const fetchInit: RequestInit & { next?: { revalidate?: number } } = {};
  if (opts.revalidate !== undefined) {
    fetchInit.next = { revalidate: opts.revalidate };
  } else {
    fetchInit.cache = opts.cache ?? "no-store";
  }
  // r140 — thread the optional AbortSignal so client pollers can cancel
  // in-flight fetches on unmount (code-reviewer R2 fix).
  if (opts.signal) {
    fetchInit.signal = opts.signal;
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
  /** r142 — 1-line explanation citing values + source. Populated by the
   *  engine layer (`assess_confluence()` Driver dataclass) ; null for
   *  legacy LLM-narrative entries (pre-r142 cards). */
  evidence?: string | null;
  /** r142 — Provenance tag (e.g. `fred:DGS10`, `cot:CFTC_EUR`). Engine
   *  layer only ; null for LLM-narrative. */
  source?: string | null;
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

/** r95 (ADR-104, migration 0050) — one stale/absent critical FRED anchor
 *  that silently degraded a section/sub-driver, frozen at card generation.
 *  Mirror of the backend `DegradedInputOut` (schemas.py SSOT). */
export interface DegradedInput {
  series_id: string;
  status: "stale" | "absent";
  /** ISO date (YYYY-MM-DD) of the last ingested observation ; null when
   *  the series was never ingested (status === "absent"). */
  latest_date: string | null;
  age_days: number | null;
  max_age_days: number;
  /** which section / sub-driver this anchor reduces reliability on. */
  impacted: string;
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

  // r95 (ADR-104, migration 0050) — FRED-liveness degraded-input
  // manifest frozen at card generation. DELIBERATE TRI-STATE (mirrors
  // the backend nullable-no-default column) : `null` = liveness not
  // tracked at this card's generation (legacy/pre-0050 card — honest
  // "unknown", NOT "all fresh") ; `[]` = tracked, all critical anchors
  // fresh ; non-empty = generated on degraded inputs. The r96
  // DataIntegrityBadge consumes ONLY this card field (ADR-104
  // §Cross-endpoint — never the live /v1/data-pool recompute).
  degraded_inputs: DegradedInput[] | null;

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

/** r68 — fetch the upcoming economic calendar from `/v1/calendar/upcoming`.
 *  r140 — optional `since_minutes` extends the window backward so the
 *  `<FreshDataBanner>` can detect catalysts whose `scheduled_at` elapsed
 *  since the briefing's `generated_at` (lesson #11 honest scope : surfaces
 *  scheduled-time-elapsed, NOT actual-value-published).
 *  Optional `asset` filter narrows via affected_assets[] mapping.
 */
export async function getCalendarUpcoming(
  asset: string | null = null,
  sinceMinutes: number = 0,
  opts: { signal?: AbortSignal } = {},
): Promise<CalendarUpcoming | null> {
  const qs = new URLSearchParams();
  if (asset) qs.set("asset", asset);
  if (sinceMinutes > 0) qs.set("since_minutes", String(sinceMinutes));
  const path = qs.toString() ? `/v1/calendar/upcoming?${qs.toString()}` : "/v1/calendar/upcoming";
  // r140 — pass `signal` so FreshDataBanner's AbortController actually
  // cancels in-flight polls on unmount (code-reviewer R2 fix).
  // Conditionally include signal to honour exactOptionalPropertyTypes.
  const apiOpts: { signal?: AbortSignal } = {};
  if (opts.signal) apiOpts.signal = opts.signal;
  return apiGet<CalendarUpcoming>(path, apiOpts);
}

/** r89 (ADR-099 Tier 2.3) — themed Polymarket prediction-market impact
 *  from `/v1/polymarket-impact` (themes + per-asset transmission).
 *  Reuses the existing `PolymarketImpact` type (declared below). The
 *  standalone `/polymarket` route calls this endpoint inline with
 *  query params ; the briefing wants the default themed view. */
export async function getPolymarketImpact(): Promise<PolymarketImpact | null> {
  return apiGet<PolymarketImpact>("/v1/polymarket-impact");
}

/** r152 — Engine 8 forward-looking surface from
 *  `/v1/event-anticipation/{asset}`. Returns the composed
 *  `EventAnticipationOut` with mode "engaged" / "standby" / "silent" so
 *  the dedicated `<EventAnticipationPanel>` can dispatch off `data.mode`.
 *
 *  Pure server-side fetch (no signal needed — briefing SSR Promise.all). */
export async function getEventAnticipation(asset: string): Promise<EventAnticipationOut | null> {
  // Normalise EUR-USD / eur_usd → EUR_USD to match the router path
  // pattern `^[A-Z]{3,8}_[A-Z]{3,8}$|^[A-Z]{3,8}$`.
  const normalised = asset.toUpperCase().replace(/-/g, "_");
  return apiGet<EventAnticipationOut>(`/v1/event-anticipation/${encodeURIComponent(normalised)}`);
}

/** r161 Strand G — fetch ADR-106 SessionVerdict for the asset's current-day
 *  NY-session window. Returns null on 404 (no card today yet OR Pass-6 dormant
 *  → builder returns downgraded verdict, but apiGet would surface a 404 if no
 *  card exists at all) OR any apiGet failure (network, 5xx). Frontend renders
 *  honest absence when null — doctrine #11 calibrated honesty mirror of
 *  EventAnticipationPanel's shouldRenderPanel pattern.
 *
 *  Endpoint contract per ADR-106 D5 : GET /v1/verdict/session-ny/{asset}
 *  Path-param regex mirrors event_anticipation (CRIT-1 fix accepts digit
 *  prefixes for NAS100/SPX500). */
export async function getSessionVerdict(asset: string): Promise<SessionVerdict | null> {
  const normalised = asset.toUpperCase().replace(/-/g, "_");
  return apiGet<SessionVerdict>(`/v1/verdict/session-ny/${encodeURIComponent(normalised)}`);
}

/** r162 Stride 8 Phase 2 — fetch ADR-106 CoachMacroContext (asset-agnostic).
 *  Returns null on any apiGet failure (network / 5xx) — the panel renders
 *  honest absence in that case (doctrine #11 calibrated-honesty surface).
 *
 *  The backend builder always returns a fully-populated CoachMacroContext
 *  even when classifiers are inconclusive (`cycle="uncertain"` /
 *  `dominant_theme=null` / `top_next_surprises=[]` are LEGITIMATE doctrine
 *  #11 outputs — the panel surfaces them with explicit honest-uncertainty
 *  chrome rather than hiding the section). Pure server-side fetch (SSR
 *  Promise.all). LIVE state — backend sets `Cache-Control: private,
 *  no-store`. */
export async function getCoachMacroContext(): Promise<CoachMacroContext | null> {
  return apiGet<CoachMacroContext>("/v1/coach-macro-context");
}

/** Cross-asset USD coherence — one asset's contribution to the dollar read. */
export interface DollarCoherenceView {
  asset: string;
  bias: string;
  conviction: number;
  stance: string; // usd_up | usd_down | neutral
  weight: number;
}

/** Cross-asset USD coherence verdict (GET /v1/dollar-coherence). Reconciles
 *  the day's per-asset bias cards into ONE dollar read + flags the assets
 *  whose bias fights the consensus. Descriptive only (ADR-017). */
export interface DollarCoherenceData {
  consensus: string; // usd_up | usd_down | mixed | neutral
  consensus_strength: number;
  coherent: boolean;
  n_directional: number;
  outliers: string[];
  recommended_demotions: Record<string, number>;
  views: DollarCoherenceView[];
  coach_explanation: string;
}

/** Fetch the cross-asset USD-coherence verdict (asset-agnostic, SSR). Returns
 *  null on apiGet failure → the lens renders honest absence. The backend
 *  degrades honestly (consensus="neutral" + coherent=true when <2 directional
 *  cards), so a non-null response with consensus="neutral" is legitimate. */
export async function getDollarCoherence(): Promise<DollarCoherenceData | null> {
  return apiGet<DollarCoherenceData>("/v1/dollar-coherence");
}

/** mission-7 — one point on the market-implied Fed-funds path (ZQ futures). */
export interface StirPoint {
  series_id: string;
  month_label: string;
  implied_effr: number | null;
  observation_date: string | null;
  cum_bps_vs_front: number | null;
  repricing_bps: number | null;
  sessions_in_window: number;
}

/** mission-7 — per-FOMC-meeting market-implied outcome (CME FedWatch). */
export interface StirMeeting {
  label: string;
  decision_date: string;
  implied_change_bps: number | null;
  p_cut: number | null;
  p_hold: number | null;
  p_hike: number | null;
}

/** mission-7 — `/v1/stir` market-implied Fed path + ~5-session repricing
 *  delta + per-meeting FedWatch probabilities. Pure-data route (not
 *  AI-watermarked). Returns null on apiGet failure → <StirPanel> renders
 *  honest absence (doctrine #11). */
export interface StirData {
  as_of: string | null;
  policy_rate_effr: number | null;
  front_implied_effr: number | null;
  points: StirPoint[];
  meetings: StirMeeting[];
  horizon_label: string | null;
  net_bps_to_horizon: number | null;
  cuts_priced_to_horizon: number | null;
  tone: string;
  repricing_bps_horizon: number | null;
  note: string;
  sources: string[];
}

export async function getStir(): Promise<StirData | null> {
  return apiGet<StirData>("/v1/stir");
}

/**
 * r69 + r138 — fetch recent news items from `/v1/news`.
 *
 * r138 — backend now returns a `NewsListEnvelope` envelope `{ items, filter }`
 * so the asset-filter status can be surfaced honestly (lesson #11 calibrated).
 * `asset` (optional, ADR-099 §D-1 5-asset surface or backend legacy 9-asset map)
 * narrows the feed to items keyword-matching the asset's ticker / institutional
 * terms with the SAME scarce-fallback discipline as `services/data_pool._section_news`
 * (re-homed to `services/asset_news_affinity`).
 *
 * Returns the full envelope so callers can render the filter disclosure ;
 * panels that only need the items can read `.items`.
 */
export interface NewsFilterMeta {
  asset: string;
  matched: number;
  applied: boolean;
  min_required: number;
  known_asset: boolean;
}

export interface NewsListEnvelope {
  items: NewsItem[];
  filter: NewsFilterMeta | null;
}

export async function getNews(
  limit = 12,
  asset: string | null = null,
): Promise<NewsListEnvelope | null> {
  const qs = new URLSearchParams({ limit: String(limit) });
  if (asset) qs.set("asset", asset);
  return apiGet<NewsListEnvelope>(`/v1/news?${qs.toString()}`);
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

// r120 — hourly-volatility seasonality (24-bar UTC median + p75 |log-rdt|
// bp). The SINGLE source of the `/v1/hourly-volatility` URL + opts, shared
// by the standalone `/hourly-volatility/[asset]` page AND the primary
// `/briefing/[asset]` page (doctrine #9 anti-accumulation — one fetch
// definition, two callers). Mirrors `getIntradayBars`.
export async function getHourlyVol(asset: string): Promise<HourlyVolOut | null> {
  return apiGet<HourlyVolOut>(`/v1/hourly-volatility/${encodeURIComponent(asset)}?window_days=30`, {
    revalidate: 300,
  });
}

// r123 — server-side fetch of the DST-correct session-status (the
// `SessionStatus` client chip fetches it independently with `no-store` and
// a 5-min self-heal poll ; this server-side wrapper lets the briefing page
// SSR pass the canonical state to `<TodaySessionPulse>` for the live
// session-window stats — `<TodaySessionPulse>` is RSC-safe by design and
// cannot fetch on its own, lesson #5 RSC-leak discipline). 60s ISR is
// generous enough that the chip's client-side 5-min refresh remains the
// authoritative live source ; this server slice is the SSR seed.
export async function getSessionStatus(): Promise<SessionStatusOut | null> {
  return apiGet<SessionStatusOut>("/v1/calendar/session-status", { revalidate: 60 });
}

// r127 — per-asset tempo threshold map fetched from `/v1/tempo-thresholds`
// (Mission centrale Axis-7 auto-amélioration consumer view ; backend
// shipped r126 commit d460b97). Returns a `Record<asset, thresholds>` map
// the briefing page passes to `derivePulse(..., thresholdsOverride)` as
// the LIVE recalibrated thresholds ; on API error / empty rows / cold-
// start the briefing falls back to the r125 hardcoded
// `TEMPO_THRESHOLDS_BY_ASSET` in `lib/sessionPulse.ts`. The endpoint emits
// `Cache-Control: public, max-age=300, stale-while-revalidate=900` ; the
// 300s ISR here matches the server-side hint so Next.js + CDN stay coherent.
//
// Shape transform : the API returns `{ items: TempoThresholdItem[] }` ; we
// flatten to `Record<asset, { breakout, active, trending, range_bound }>`
// inline so the consumer side never sees the wrapped list shape (smaller
// surface area for the `derivePulse` signature).
interface TempoThresholdItem {
  asset: string;
  breakout_bp: number;
  active_bp: number;
  trending_bp: number;
  range_bound_bp: number;
  sample_size: number;
  window_days: number;
  computed_at: string;
}

interface TempoThresholdsListOut {
  items: TempoThresholdItem[];
}

/** r127 — flat per-asset shape (matches `lib/sessionPulse.ts TempoThresholds`).
 * Re-declared here as a structural type — keeping the dependency direction
 * `sessionPulse → api` would be wrong ; api should not import from sessionPulse.
 * The two declarations are byte-identical and pinned by a vitest contract
 * test in `__tests__/sessionPulse.test.ts` (drift-guard). */
export interface TempoThresholdsForAsset {
  breakout: number;
  active: number;
  trending: number;
  range_bound: number;
}

/** r129 — per-asset calibration metadata (ADR-104 data-honesty staleness
 * banner, the r127 trader NIT closure). Carries the freshness anchor that
 * the `<TodaySessionPulse>` panel surfaces under the tempo meter so Eliot
 * can SEE how stale the calibration is + how many samples backed it. */
export interface TempoMetadata {
  /** ISO datetime of the recalibration cron fire that produced these
   * thresholds. Parsed client-side via `new Date(...)` to compute a
   * staleness-in-days delta. */
  computed_at: string;
  /** Number of Paris-day samples in the percentile calibration window. */
  sample_size: number;
  /** Rolling window in days (the cron's `--window-days` ; default 90). */
  window_days: number;
}

/** r129 — envelope shape for `getTempoThresholds()` carrying BOTH the
 * thresholds (consumed by derivePulse for label classification) AND the
 * metadata (surfaced by TodaySessionPulse's data-honesty banner). The
 * shape is per-asset on both keys so a future cron that fires per-asset
 * (rather than all-5 in one transaction) can produce divergent metadata
 * cleanly. r127's flat-Record shape is REPLACED — the briefing page is
 * the only consumer + has been updated in the same r129 commit. */
export interface TempoThresholdsBundle {
  thresholds: Record<string, TempoThresholdsForAsset>;
  metadata: Record<string, TempoMetadata>;
}

/** Fetches `/v1/tempo-thresholds` and flattens the list into the r129
 * envelope shape `{ thresholds, metadata } | null`. Returns `null` when
 * the API is unreachable OR the cron hasn't yet populated any rows — the
 * briefing page falls back to the r125 hardcoded `TEMPO_THRESHOLDS_BY_ASSET`
 * in that case (data-honesty : the worst case is "label is slightly stale",
 * never "label is missing"). r129 NOTE — both `thresholds` and `metadata`
 * fall together (same upstream rows from the cron INSERT transaction) ;
 * a future divergence path (per-asset partial cron success) would extend
 * the envelope rather than splitting into two fetchers. */
export async function getTempoThresholds(): Promise<TempoThresholdsBundle | null> {
  const list = await apiGet<TempoThresholdsListOut>("/v1/tempo-thresholds", {
    revalidate: 300,
  });
  if (list === null) return null;
  if (!list.items || list.items.length === 0) {
    // Y-3 (code-reviewer r127) : distinguish "API down (warned by apiGet)"
    // from "cron hasn't fired yet (expected cold state)" in dev logs.
    // Both collapse to `null` for the consumer (fall back to r125
    // hardcoded), but the dev observability surface stays distinct.
    // `info` level — this is an expected boot state, not an error.
    console.info(
      "[api] /v1/tempo-thresholds returned 0 items — falling back to r125 hardcoded TEMPO_THRESHOLDS_BY_ASSET (cron not fired or sample too small)",
    );
    return null;
  }
  const thresholds: Record<string, TempoThresholdsForAsset> = {};
  const metadata: Record<string, TempoMetadata> = {};
  for (const item of list.items) {
    thresholds[item.asset] = {
      breakout: item.breakout_bp,
      active: item.active_bp,
      trending: item.trending_bp,
      range_bound: item.range_bound_bp,
    };
    metadata[item.asset] = {
      computed_at: item.computed_at,
      sample_size: item.sample_size,
      window_days: item.window_days,
    };
  }
  return { thresholds, metadata };
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

/** r138 — disclosed asset-filter status (lesson #11 calibrated honesty). */
export interface GeopoliticsFilterMeta {
  asset: string;
  matched: number;
  applied: boolean;
  min_required: number;
  known_asset: boolean;
}

export interface GeopoliticsBriefing {
  gpr: GprReading | null;
  gdelt_window_hours: number;
  n_events_window: number;
  gdelt_negatives: GdeltNegative[];
  /** r138 — `null` for back-compat when `?asset=` is not supplied. */
  filter?: GeopoliticsFilterMeta | null;
}

/**
 * r77 + r138 — fetch the geopolitics briefing from `/v1/geopolitics/briefing`.
 *
 * r138 — optional `asset` narrows the GDELT most-negative ranking to events
 * whose title / query_label / URL match the asset's keyword affinity, with
 * the same scarce-fallback rule as `/v1/news`. AI-GPR (single global index)
 * is returned unchanged. Frontend can render the filter disclosure from
 * `.filter`.
 */
export async function getGeopoliticsBriefing(
  hours = 48,
  top = 6,
  asset: string | null = null,
): Promise<GeopoliticsBriefing | null> {
  const qs = new URLSearchParams({ hours: String(hours), top: String(top) });
  if (asset) qs.set("asset", asset);
  return apiGet<GeopoliticsBriefing>(`/v1/geopolitics/briefing?${qs.toString()}`);
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

// r84 — Phase-D pocket skill (Vovk-AA aggregator self-assessment).
// Mirror of apps/api routers/phase_d.py PocketSummaryOut. The system's
// HONEST historical discrimination skill per (asset,regime) pocket :
// skill_delta = prod_predictor_weight − equal_weight_weight. Negative
// = the LLM forecaster has historically done WORSE than a no-info
// baseline on this pocket (anti-skill → weight its read down). LIVE at
// /v1/phase-d/* but never surfaced to the trader until now.
export interface PocketSummary {
  asset: string;
  regime: string;
  pocket_version: number;
  prod_predictor_weight: number;
  climatology_weight: number;
  equal_weight_weight: number;
  n_observations: number;
  has_skill_vs_baseline: boolean;
  skill_delta: number;
  latest_drift_event_at: string | null;
  active_addenda_count: number;
  pocket_updated_at: string;
}

export interface PocketSummaryList {
  rows: PocketSummary[];
  count: number;
  asset_filter: string | null;
  regime_filter: string | null;
  pocket_version: number;
}

/** r84 — per-asset Phase-D pocket skill from `/v1/phase-d/pocket-summary`. */
export async function getPocketSummary(asset: string): Promise<PocketSummaryList | null> {
  return apiGet<PocketSummaryList>(`/v1/phase-d/pocket-summary?asset=${encodeURIComponent(asset)}`);
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
  /** r131 axis-8 Δ-YES — YES from oldest snapshot in 24h-48h-ago window
   * for this slug. `null` when no history (market <24h or cron gap). */
  yes_24h_ago?: number | null;
  /** r131 axis-8 Δ-YES — signed shift in pp over last 24h. `null` when
   * `yes_24h_ago` is null. Consumed by `<PolymarketImpactPanel>` for
   * velocity badge with tone escalation `|v|>5pp` shift rapide,
   * `>10pp` manipulation possible (descriptive, ADR-017). */
  yes_velocity_pp?: number | null;
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

// r145 — recent published economic event actuals + r141 surprise classifier
// projection. Mission centrale axis-5 user-surface visibility (was infra-
// only since r141 schema + r144 reconciler).
//
// ADR-017 boundary : 5-state geometric vocabulary, signed magnitude in % of
// |consensus|. NEVER directional. Per-asset transmission left to the
// verdict/confluence layers (parity with MacroSurprisePanel doctrine).
//
// r145 reality : state is `unavailable` for all rows today because the
// analyst range envelope provider is not yet wired (r146+). `magnitude_pct`
// IS populated from the FF consensus point. When the range provider lands,
// state badges auto-light up without UI changes.
export type SurpriseState =
  | "unavailable"
  | "in_range"
  | "above_range"
  | "below_range"
  | "exact_consensus";

export interface SurpriseClassificationOut {
  state: SurpriseState;
  actual_value: number | null;
  consensus_value: number | null;
  forecast_min_value: number | null;
  forecast_max_value: number | null;
  magnitude_pct: number | null;
  range_breach: number | null;
  parse_failures: string[];
}

export interface RecentActualRow {
  event_id: string;
  currency: string;
  scheduled_at_utc: string;
  title: string;
  impact: "high" | "medium" | "low";
  actual: string;
  forecast: string | null;
  forecast_min: string | null;
  forecast_max: string | null;
  previous: string | null;
  url: string | null;
  classification: SurpriseClassificationOut;
}

export interface RecentActuals {
  generated_at: string;
  lookback_days: number;
  currency: string | null;
  rows: RecentActualRow[];
}

/**
 * r152 — Engine 8 Event-Driven anticipation wire shape, mirrors the
 * backend `EventAnticipationView` / `EventProximityFactor` dataclasses.
 *
 * Three modes :
 *   - "engaged"  : Engine 8 fires (event in 48h window, mapped class).
 *                  `engaged` populated with full factor projection.
 *   - "standby"  : Engine 8 silent (no event in 48h), but next 1-3
 *                  high/medium-impact events exist in the next 14d.
 *                  `standby_events` populated.
 *   - "silent"   : nothing in 14d window. Honest empty state — panel
 *                  may still render explanatory chrome OR return null.
 *
 * ADR-017 boundary : DESCRIPTIVE drift expectation (geometric direction
 * + signed magnitude_bp + literature-anchored caveat) ; NEVER imperative.
 * Sign is stripped at the UI boundary per r142 trader RED-1 doctrine —
 * the engine internal sign is an INTERNAL aggregation convention.
 */
export type EventAnticipationMode = "engaged" | "standby" | "silent";

export type DriftDirection = "up" | "down" | "unknown";

export type EventConfidence = "high" | "medium" | "low" | "unavailable";

export type VixRegimeGate = "above_p75" | "p50_to_p75" | "below_p50" | "unavailable";

export interface EventProximityFactorOut {
  next_event_id: string | null;
  next_event_title: string | null;
  next_event_currency: string | null;
  next_event_minutes_until: number | null;
  next_event_impact: "high" | "medium" | "low" | null;
  next_event_class: string | null;
  expected_drift_direction: DriftDirection;
  expected_drift_magnitude_bp: number | null;
  confidence: EventConfidence;
  vix_regime_gate: VixRegimeGate;
  caveat: string;
  literature_anchor: string;
  parse_failures: string[];
}

export interface UpcomingEventOut {
  event_id: string;
  currency: string;
  scheduled_at_utc: string;
  title: string;
  impact: "high" | "medium";
  event_class: string | null;
  minutes_until: number;
}

export interface EventAnticipationOut {
  generated_at: string;
  asset: string;
  mode: EventAnticipationMode;
  engaged: EventProximityFactorOut | null;
  standby_events: UpcomingEventOut[];
  parse_failures: string[];
}

/* ─────────────────────────── r161 Strand G — ADR-106 SessionVerdict ── */

export type VerdictDirection = "up" | "down" | "neutral";
export type VerdictNature = "structured" | "momentum" | "range_bound" | "uncertain";
/** r167 G1 — TradeabilityFlag : closes Eliot's #1 CRITICAL gap from
 *  his trading methodology transcript (Fathom 2026-05-25 §VIII).
 *  Surfaces a HONEST DISCLOSURE when the day is structurally unsuitable
 *  for taking a NY-session position (bank holiday / pending event /
 *  abnormally low volatility / market range / no strong setup).
 *  Mirror of ``packages/ichor_brain/.../session_verdict.py:TradeabilityFlag``. */
export type TradeabilityFlag =
  | "tradeable"
  | "no_setup"
  | "holiday"
  | "event_freeze"
  | "low_volatility"
  | "range";
export type LiveTriggerType =
  | "economic_release"
  | "central_bank_speech"
  | "news_headline"
  | "polymarket_shift"
  | "cross_asset_breakout"
  | "scenario_invalidation"
  | "scenario_confirmation";
export type LiveTriggerImpact = "confirms_verdict" | "tests_verdict" | "invalidates_verdict";
export type PriorityAsset = "EUR_USD" | "GBP_USD" | "XAU_USD" | "SPX500_USD" | "NAS100_USD";
export type BucketLabel =
  | "crash_flush"
  | "strong_bear"
  | "mild_bear"
  | "base"
  | "mild_bull"
  | "strong_bull"
  | "melt_up";

export interface LiveTrigger {
  trigger_type: LiveTriggerType;
  description: string;
  fired_at_utc: string;
  impact: LiveTriggerImpact;
  source: string;
}

export interface ScenarioInvalidationState {
  scenarios_invalidated_hard: BucketLabel[];
  scenarios_invalidated_soft: BucketLabel[];
  scenarios_with_notes: BucketLabel[];
  last_check_utc: string;
}

export interface SessionVerdict {
  asset: PriorityAsset;
  session_window: "ny_13h_to_20h_paris";
  direction: VerdictDirection;
  conviction_pct: number;
  nature: VerdictNature;
  derived_from_scenarios: boolean;
  scenario_decomposition_id: string | null;
  invalidation_state: ScenarioInvalidationState | null;
  live_triggers: LiveTrigger[];
  coach_explanation: string;
  ne_pas_actionner_avant_paris: string;
  couper_au_plus_tard_paris: string;
  last_updated_utc: string;
  expires_at_utc: string;
  /** r167 G1 — TradeabilityFlag derived from tradeability_evaluator
   *  composite rule (priority : holiday > event_freeze > low_volatility >
   *  range > no_setup > tradeable). Default ``"tradeable"`` preserves
   *  backward-compat with pre-r167 emissions. */
  tradeability: TradeabilityFlag;
}

/* ─────────────────────── r162 Stride 8 Phase 2 — ADR-106 CoachMacroContext ── */

/** 4-phase business-cycle classification per the Hewi Capital trader transcript
 *  framework (growth × inflation 2×2 matrix). `uncertain` is a legitimate
 *  doctrine #11 calibrated-honesty output when FRED data is stale (>= 45 days)
 *  OR one axis is genuinely ambiguous (mirror of `coach_macro_context.py:101`). */
export type BusinessCycle = "expansion" | "reflation" | "deflation" | "stagflation" | "uncertain";

/** Coarse growth axis label — surfaced standalone as a frontend chip
 *  ("Croissance: forte"). Sourced from PAYEMS m/m trend over last 90d. */
export type GrowthSignal = "strong" | "weak" | "uncertain";

/** Coarse inflation axis label — surfaced standalone as a frontend chip
 *  ("Inflation: en hausse"). Sourced from CPIAUCSL 3-month direction. */
export type InflationSignal = "rising" | "falling" | "uncertain";

/** Canonical 8-driver macro theme literal (single source of truth :
 *  `packages/agents/.../macro.py:24-33` ; mirrored in
 *  `packages/ichor_brain/.../coach_macro_context.py:65-74` for the Pydantic
 *  Literal). The dominant theme is classified by rule-based max |z-score|
 *  over the 18 FRED series mapped in `coach_macro_context_builder.py:_SERIES_TO_THEME`. */
export type MacroTheme =
  | "monetary_policy"
  | "growth_data"
  | "inflation_data"
  | "labor_market"
  | "fiscal_policy"
  | "geopolitics"
  | "credit_conditions"
  | "commodity_supply";

/** Surprise priority tier — drives UI emphasis on the upcoming-events list.
 *  Sourced from `_surprise_priority(title, impact, cycle)` cycle-aware rule. */
export type SurprisePriority = "high" | "medium" | "low";

/** r168 G3 — Risk-on / risk-off / transitional ambient regime label.
 *  Eliot's §X verbatim pillar ("régime risk on ou risk off"). Self-calibrating
 *  z-score classifier in backend `coach_macro_context_builder._classify_risk_regime`
 *  over VIXCLS + BAMLH0A0HYM2 FRED series (252d rolling window). Pattern #15 R59
 *  immune by design (sigma-based thresholds, no peer-reviewed citation claim).
 *  Mirror of `packages/ichor_brain/.../coach_macro_context.py` RiskRegime Literal. */
export type RiskRegime = "risk_on" | "risk_off" | "transitional";

/** One upcoming high/medium-impact event surfaced for the coach narrative.
 *  Mirror of `CalendarSurprise` Pydantic (frozen, extra=forbid). */
export interface CalendarSurprise {
  event_label: string;
  scheduled_at_paris: string;
  priority: SurprisePriority;
  why_it_matters: string;
}

/** Canonical Ichor coach macro narrative — rendered at the TOP of
 *  `/briefing/[asset]` ABOVE `<SessionVerdictPanel>` per ADR-106 §"coach
 *  explicateur". Materialises Eliot's r161 directive verbatim ("coach de
 *  compréhension", "guide lumineux qui rend chaque élément limpide"). */
export interface CoachMacroContext {
  cycle: BusinessCycle;
  cycle_confidence_pct: number;
  growth_signal: GrowthSignal;
  inflation_signal: InflationSignal;
  dominant_theme: MacroTheme | null;
  dominant_theme_strength_z: number | null;
  /** r168 G3 — Eliot's §X risk-on/off pillar. Default `"transitional"` for
   *  backward-compat with pre-r168 wire responses. */
  risk_regime: RiskRegime;
  /** r168 G3 — Up to 3 mechanical evidence strings (e.g. `"VIXCLS z=+1.23σ"`).
   *  Empty when `risk_regime === "transitional"` and no signal crossed ±0.7σ. */
  risk_regime_evidence: string[];
  top_next_surprises: CalendarSurprise[];
  coach_paragraph: string;
  data_freshness_days: number;
  generated_at_utc: string;
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
