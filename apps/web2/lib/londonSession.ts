/**
 * londonSession.ts — §6.2 — London-morning read pure helpers + FR copy
 * SSOTs consumed by `<LondonSessionPanel>`.
 *
 * Eliot §6.2 CAPITAL point : read how the asset traded during the LONDON
 * MORNING (the session running before / into the NY open) to calibrate the
 * upcoming NY-session view. Backend endpoint `GET /v1/london-session/{asset}`
 * returns `LondonSessionOut`.
 *
 * ADR-017 boundary : GEOMETRIC labels for how the London morning traded,
 * NEVER a directional signal for the NY session. The panel is calibration
 * CONTEXT for the trader's own read, not a buy/sell instruction.
 *
 * Doctrine #5 (RSC client-boundary) : PURE module (no React, no JSX, no
 * "use client").
 */

/* ─────────────────────────────────── DOMAIN ──────────────────────── */

export type LondonDirectionKey = "up" | "down" | "range";

export type LondonActivityKey = "active" | "calm" | "normal";

/** Thresholds mirror the backend `_section_london_session` prose tags. */
const ACTIVE_RATIO = 1.4;
const CALM_RATIO = 0.6;
/** Activity meter caps the displayed range ratio so an outlier morning
 *  doesn't blow out the bar. */
export const RATIO_DISPLAY_CAP = 3.0;

/* ─────────────────────────────────── FR COPY SSOT ────────────────── */

/** Short FR label per direction. Doctrine #4 SSOT. */
export const LONDON_DIRECTION_LABEL_FR: Record<LondonDirectionKey, string> = {
  up: "Haussière",
  down: "Baissière",
  range: "En range",
};

/** One-sentence FR explainer per direction — plain coach voice. */
export const LONDON_DIRECTION_HINT_FR: Record<LondonDirectionKey, string> = {
  up: "Londres a poussé à la hausse ce matin (le corps de la bougie fait ≥ 30 % du range) : les acheteurs ont tenu la main.",
  down: "Londres a poussé à la baisse ce matin (le corps de la bougie fait ≥ 30 % du range) : les vendeurs ont tenu la main.",
  range:
    "Matinée sans direction nette (corps < 30 % du range) : le marché hésite et semble attendre un catalyseur.",
};

/** Tailwind v4 tone token per direction (matches the sibling session-context
 *  panel : cobalt for up, danger-red for down, muted for range). */
export const LONDON_DIRECTION_TONE: Record<LondonDirectionKey, string> = {
  up: "text-[var(--color-accent-1)]",
  down: "text-[var(--color-text-danger)]",
  range: "text-[var(--color-text-muted)]",
};

/** Short FR label per activity level. */
export const LONDON_ACTIVITY_LABEL_FR: Record<LondonActivityKey, string> = {
  active: "Séance active",
  calm: "Séance calme",
  normal: "Activité normale",
};

/** Tone token per activity level. */
export const LONDON_ACTIVITY_TONE: Record<LondonActivityKey, string> = {
  active: "text-[var(--color-accent-2)]",
  calm: "text-[var(--color-text-muted)]",
  normal: "text-[var(--color-text-secondary)]",
};

/* ─────────────────────────────────── DERIVED ─────────────────────── */

/** Classify the morning's activity from the range ratio vs the 5-day
 *  baseline. Returns null when no baseline exists yet (honest, not a
 *  fabricated "normal"). */
export function classifyLondonActivity(ratio: number | null | undefined): LondonActivityKey | null {
  if (ratio === null || ratio === undefined || Number.isNaN(ratio)) return null;
  if (ratio >= ACTIVE_RATIO) return "active";
  if (ratio <= CALM_RATIO) return "calm";
  return "normal";
}

/** One coach sentence : what this London read suggests to WATCH at the NY
 *  open. ADR-017 : calibration CONTEXT, never a directional instruction. */
export function londonCalibrationHint(
  direction: LondonDirectionKey,
  activity: LondonActivityKey | null,
): string {
  if (direction !== "range" && activity === "active") {
    return "Une matinée Londres directionnelle ET active prolonge souvent le mouvement à l'ouverture de New York : surveille la continuité plutôt que le retournement.";
  }
  if (direction === "range" || activity === "calm") {
    return "Une matinée Londres en range ou calme suggère que le marché attend un catalyseur : la vraie direction se décide souvent à l'open de New York.";
  }
  return "Matinée d'activité normale : contexte neutre, à confirmer par le comportement à l'ouverture de New York.";
}

/* ─────────────────────────────────── HELPERS ─────────────────────── */

/** Format a UTC ISO datetime as « il y a N min » FR relative time.
 *  Kept local (not cross-imported) per Doctrine #5 client-boundary. */
export function formatFreshness(computedAtUtc: string | null | undefined): string {
  if (!computedAtUtc) return "—";
  const d = new Date(computedAtUtc);
  if (Number.isNaN(d.getTime())) return "—";
  const diffMin = Math.floor((Date.now() - d.getTime()) / 60_000);
  if (diffMin < 1) return "à l'instant";
  if (diffMin < 60) return `il y a ${diffMin} min`;
  const diffH = Math.floor(diffMin / 60);
  if (diffH < 24) return `il y a ${diffH} h`;
  return `il y a ${Math.floor(diffH / 24)} j`;
}

/** FX/XAU get 5 decimals, equity indices (>= 100) get 2. */
export function formatPrice(price: number | null | undefined): string {
  if (price === null || price === undefined || Number.isNaN(price)) return "—";
  if (Math.abs(price) >= 100) return price.toFixed(2);
  return price.toFixed(5);
}

/** Signed price delta with an explicit + / − sign (the morning's net move).
 *  Sign is descriptive of the move, NEVER a buy/sell hint. */
export function formatSignedPrice(net: number | null | undefined): string {
  if (net === null || net === undefined || Number.isNaN(net)) return "—";
  const sign = net >= 0 ? "+" : "−";
  return `${sign}${formatPrice(Math.abs(net))}`;
}

/** Range ratio as « 1.4× » or em-dash when no baseline. */
export function formatRatio(ratio: number | null | undefined): string {
  if (ratio === null || ratio === undefined || Number.isNaN(ratio)) return "—";
  return `${ratio.toFixed(1)}×`;
}

const _MONTHS_FR = [
  "janvier",
  "février",
  "mars",
  "avril",
  "mai",
  "juin",
  "juillet",
  "août",
  "septembre",
  "octobre",
  "novembre",
  "décembre",
];

/** « 2026-06-01 » → « 1 juin ». Pure, no Date() needed for a YYYY-MM-DD. */
export function formatSessionDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso);
  if (!m) return iso;
  const month = _MONTHS_FR[Number(m[2]) - 1] ?? "";
  return `${Number(m[3])} ${month}`;
}

/** Freshness badge label for the live vs last-session distinction. */
export function freshnessLabel(isToday: boolean, sessionDate: string): string {
  return isToday ? "ce matin · en direct" : `dernière séance · ${formatSessionDate(sessionDate)}`;
}

/** Equity indices don't trade during the London FX morning, so an absent read
 *  for them is STRUCTURAL (not a data gap). Used to give an honest,
 *  asset-aware absence message rather than implying a holiday. */
const _EQUITY_INDEX_ASSETS = new Set(["SPX500_USD", "NAS100_USD", "US30_USD", "US2000_USD"]);

export function isEquityIndex(asset: string): boolean {
  return _EQUITY_INDEX_ASSETS.has(asset);
}

/** For equity indices, a NON-today read is stale noise (they don't trade the
 *  London morning meaningfully — at best some ETF/futures pre-market overlap),
 *  so a 3-day-old read dressed as "calibration for NY" misleads. Show the
 *  structural absence instead. FX/metals keep a clearly-labelled « dernière
 *  séance » read, which is genuinely useful pre-open. Coherence discipline :
 *  never present a stale index read as live calibration (the 2026-05-29
 *  stale-as-real lesson). */
export function shouldShowLondonRead(asset: string, isToday: boolean): boolean {
  return !(isEquityIndex(asset) && !isToday);
}

/** Asset-aware honest-absence copy. For equity indices the absence is
 *  structural (no London-morning equity session) — never a fabricated
 *  « week-end / jour férié ». Coherence discipline (no stale-as-real). */
export function londonAbsenceCopy(asset: string): { title: string; body: string } {
  if (isEquityIndex(asset)) {
    return {
      title: "Pas de séance de Londres pour les indices",
      body: "Les indices actions (S&P 500, Nasdaq) ne tradent pas pendant la matinée de Londres : cette lecture éclaire surtout l'EUR/USD, le GBP/USD et l'or. Pour les indices, c'est l'ouverture de New York qui fait le prix.",
    };
  }
  return {
    title: "Séance de Londres indisponible",
    body: "La fenêtre n'est pas encore ouverte, ou les données intraday manquent (week-end / jour férié). Aucune donnée n'est inventée : l'absence se lit comme un vrai manque de contexte.",
  };
}
