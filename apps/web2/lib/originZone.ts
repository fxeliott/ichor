/**
 * originZone.ts — r187 G5 — Previous-session origin zone panel pure
 * helpers + FR copy SSOTs consumed by `<PreviousSessionContextPanel>`.
 *
 * Materialises Eliot Fathom transcript §V verbatim : « savoir d'où
 * vient le mouvement de la session précédente, son zone d'origine,
 * son sens, ses hauts et bas ». Backend r184 endpoint
 * `GET /v1/origin-zone/{asset}` returns `OriginZoneOut`.
 *
 * ADR-017 boundary : GEOMETRIC/PROBABILISTIC labels for the PREVIOUS
 * session, NEVER directional bias for the CURRENT session. The panel
 * renders « session précédente Londres haussière 36 pips » as a
 * CONTEXT pane, not a directional signal for Eliot's NY 13h-20h.
 *
 * Doctrine #5 (RSC client-boundary) : this is a PURE module (no React,
 * no JSX, no "use client").
 */

/* ─────────────────────────────────── DOMAIN ──────────────────────── */

export type SessionZoneKey = "asian" | "london" | "ny";

export type OriginDirectionKey = "up" | "down" | "range";

/* ─────────────────────────────────── FR COPY SSOT ────────────────── */

/** Short pill-friendly FR label per zone. Doctrine #4 SSOT. */
export const SESSION_ZONE_LABEL_FR: Record<SessionZoneKey, string> = {
  asian: "Asiatique",
  london: "Londonienne",
  ny: "New-yorkaise",
};

/** One-sentence FR explainer per zone — describes WHEN + WHO. */
export const SESSION_ZONE_HINT_FR: Record<SessionZoneKey, string> = {
  asian:
    "Tokyo + Sydney + Hong Kong (00:00-07:00 UTC). Volume modéré, range-bound typique sauf surprise BoJ.",
  london:
    "London cash open + NY pré-open (07:00-13:00 UTC). Période la plus liquide pour le FX, premiers signaux de la journée.",
  ny: "NYSE RTH 13:30-20:00 UTC + extended FX. Zone de price-discovery dominante — le mouvement de fond se révèle ici.",
};

/** Short FR label per direction. */
export const ORIGIN_DIRECTION_LABEL_FR: Record<OriginDirectionKey, string> = {
  up: "Haussière",
  down: "Baissière",
  range: "Range / consolidation",
};

/** One-sentence FR explainer per direction. */
export const ORIGIN_DIRECTION_HINT_FR: Record<OriginDirectionKey, string> = {
  up: "Le mouvement net de la zone dominante a été à la hausse (body / range ≥ 30 %). Force directionnelle confirmée.",
  down: "Le mouvement net de la zone dominante a été à la baisse (body / range ≥ 30 %). Force directionnelle confirmée.",
  range:
    "Range-bound (body / range < 30 %) — pas de force directionnelle claire dans la zone dominante. Conditions de chop / faux-signaux.",
};

/** Tailwind v4 tone token per direction. */
export const ORIGIN_DIRECTION_TONE: Record<OriginDirectionKey, string> = {
  up: "text-[var(--color-accent-1)]",
  down: "text-[var(--color-text-danger)]",
  range: "text-[var(--color-text-muted)]",
};

/* ─────────────────────────────────── HELPERS ─────────────────────── */

/** Format a UTC ISO datetime as « il y a N min » FR relative time.
 *  Mirrors themeDominant.ts:formatFreshness — kept here as a separate
 *  symbol to avoid cross-module client imports per Doctrine #5
 *  client-boundary safety. */
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

/** Format a numeric price with appropriate precision for FX/XAU
 *  (5 decimals) vs equity indices (2 decimals). Heuristic on the
 *  price magnitude — values < 100 likely FX/XAU, values >= 100 likely
 *  equity index. */
export function formatPrice(price: number | null | undefined): string {
  if (price === null || price === undefined || Number.isNaN(price)) return "—";
  if (Math.abs(price) >= 100) return price.toFixed(2);
  return price.toFixed(5);
}

/** Format a UTC ISO datetime into a short « HH:MM UTC » label for
 *  the window-bounds display. */
export function formatWindowBound(utc: string | null | undefined): string {
  if (!utc) return "—";
  const d = new Date(utc);
  if (Number.isNaN(d.getTime())) return "—";
  const hh = String(d.getUTCHours()).padStart(2, "0");
  const mm = String(d.getUTCMinutes()).padStart(2, "0");
  return `${hh}:${mm} UTC`;
}
