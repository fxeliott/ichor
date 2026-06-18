/**
 * sessionVerdict.ts — r161 Strand G — ADR-106 SessionVerdict FR copy SSOTs +
 * derived helpers consumed by `<SessionVerdictPanel>`.
 *
 * The verdict is Ichor's canonical output per Eliot's r161 directive verbatim
 * (« hausse sur la session à 85 %, de façon structurée »). This module
 * provides ONLY the presentation layer — direction/nature FR labels, glyph
 * helpers, freshness formatter — never re-derives the verdict (the backend
 * `services/session_verdict_builder.py` is the canonical compute path,
 * doctrine #4 SSOT).
 *
 * ADR refs : ADR-106 §D4 (frontend surface), §D1 (verdict shape).
 */

import type {
  LiveTrigger,
  LiveTriggerImpact,
  SessionVerdict,
  TradeabilityFlag,
  VerdictDirection,
  VerdictNature,
} from "@/lib/api";

/* ─────────────────────────────────── FR copy SSOT — DIRECTION ── */

/** Canonical FR label per direction. Doctrine #4 SSOT — every UI surface
 *  must read from this map ; never hardcode a translation. */
export const DIRECTION_FR: Record<VerdictDirection, string> = {
  up: "Biais haussier",
  down: "Biais baissier",
  neutral: "Biais neutre",
};

/** Geometric glyph per direction (NEVER imperative — ADR-017 boundary :
 *  these glyphs describe the bias, they do not prescribe action). */
export const DIRECTION_GLYPH: Record<VerdictDirection, string> = {
  up: "▲",
  down: "▼",
  neutral: "◆",
};

/** Accent color token per direction for the prominent chip. The tokens
 *  resolve at runtime via Tailwind v4 CSS variables (no hardcoded RGB —
 *  preserves the dark/light theme parity). */
export const DIRECTION_TONE: Record<VerdictDirection, string> = {
  up: "text-[var(--color-accent-bull)]",
  down: "text-[var(--color-accent-bear)]",
  neutral: "text-[var(--color-text-muted)]",
};

/* ─────────────────────────────────── FR copy SSOT — NATURE ──── */

/** Canonical FR label per movement nature. */
export const NATURE_FR: Record<VerdictNature, string> = {
  momentum: "Momentum impulsif",
  structured: "Mouvement structuré",
  range_bound: "Range-bound",
  uncertain: "Nature incertaine",
};

/** One-sentence beginner-friendly explainer per nature. Surfaced inline
 *  in the panel without a méthodologie section per Eliot's r161 directive
 *  on intuitivity ("l'explication doit être intégrée naturellement dans
 *  la façon dont les données sont présentées — pas dans un encart séparé"). */
export const NATURE_HINT_FR: Record<VerdictNature, string> = {
  momentum: "réaction post-événement / post-news, mouvement directionnel fort",
  structured: "rythme mesuré, niveaux identifiables, mouvement gérable",
  range_bound: "faible volatilité, fade des extrêmes, prudence sur breakouts",
  uncertain: "décomposition mixte, conviction insuffisante pour trancher",
};

/* ─────────────────────────────────── FR copy SSOT — TRIGGERS ── */

/** Canonical FR label per live-trigger type. */
export const TRIGGER_TYPE_FR: Record<LiveTrigger["trigger_type"], string> = {
  economic_release: "Donnée économique",
  central_bank_speech: "Communication banque centrale",
  news_headline: "Headline d'actualité",
  polymarket_shift: "Variation Polymarket",
  cross_asset_breakout: "Cassure cross-asset",
  scenario_invalidation: "Scénario invalidé",
  scenario_confirmation: "Scénario confirmé",
};

/** Canonical FR label per trigger impact direction. */
export const TRIGGER_IMPACT_FR: Record<LiveTriggerImpact, string> = {
  confirms_verdict: "Confirme",
  tests_verdict: "Teste",
  invalidates_verdict: "Invalide",
};

/** Glyph per trigger impact — purely visual cue, ADR-017-safe. */
export const TRIGGER_IMPACT_GLYPH: Record<LiveTriggerImpact, string> = {
  confirms_verdict: "↗",
  tests_verdict: "○",
  invalidates_verdict: "✕",
};

/* ─────────────────────────────────── PURE HELPERS ───────────── */

/** Format the `last_updated_utc` ISO string into a relative "il y a N min"
 *  beginner-friendly label. Pure function ; no React, no I/O. */
export function formatRelativeUpdate(lastUpdatedUtc: string, nowUtc: Date = new Date()): string {
  const updated = new Date(lastUpdatedUtc);
  const diffMs = nowUtc.getTime() - updated.getTime();
  const diffMin = Math.floor(diffMs / 60_000);

  if (diffMin < 1) return "à l'instant";
  if (diffMin === 1) return "il y a 1 min";
  if (diffMin < 60) return `il y a ${diffMin} min`;

  const diffHr = Math.floor(diffMin / 60);
  if (diffHr === 1) return "il y a 1 h";
  if (diffHr < 24) return `il y a ${diffHr} h`;

  return "il y a > 24 h";
}

/** Return true if the verdict has expired vs the wall clock. The frontend
 *  switches to "verdict expiré, attente nouvelle session" banner past this. */
export function isVerdictExpired(verdict: SessionVerdict, nowUtc: Date = new Date()): boolean {
  return nowUtc.getTime() > new Date(verdict.expires_at_utc).getTime();
}

/** Return true when the verdict should be visually demoted (fallback path
 *  per ADR-106 D1 : Pass-6 dormant → derived_from_scenarios=false +
 *  conviction_pct=0 + nature=uncertain). The panel renders with a smaller
 *  card + a "mode dormant" badge in this case — doctrine #11 calibrated
 *  honesty surface. */
export function isVerdictDormant(verdict: SessionVerdict): boolean {
  return !verdict.derived_from_scenarios;
}

/** Bin the conviction percentage into a coarse confidence tier for the
 *  UI badge. Empirically anchored to ADR-022 cap-95 (95% = max possible)
 *  and ADR-106 D2 (15% directional dead-zone → 50% conviction = floor of
 *  meaningful read after the dead-zone applies). */
export function convictionTier(pct: number): "haute" | "modérée" | "faible" | "dormante" {
  if (pct >= 75) return "haute";
  if (pct >= 60) return "modérée";
  if (pct >= 40) return "faible";
  return "dormante";
}

/* ──────────────────────── r167 G1+G8 — TRADEABILITY ───────────── */

/** Canonical FR labels per TradeabilityFlag value. Doctrine #4 SSOT —
 *  every UI surface MUST read from this map. Mirrors the canonical
 *  TradeabilityFlag Literal from `packages/ichor_brain/session_verdict.py`.
 *  Strings are pedagogical FR pour expliquer pourquoi "ne trade pas
 *  aujourd'hui" plutôt que de juste afficher le flag technique. */
export const TRADEABILITY_FR: Record<TradeabilityFlag, string> = {
  tradeable: "Conditions favorables",
  no_setup: "Pas de setup clair",
  holiday: "Jour férié US",
  event_freeze: "Annonce économique imminente",
  low_volatility: "Volatilité anormalement basse",
  range: "Marché en range",
};

/** One-sentence FR explainer per TradeabilityFlag value. Surfaced
 *  inline under the disclosure banner so the trader understands WHY
 *  Ichor signals "ne trade pas aujourd'hui" (Eliot's discipline
 *  transcript §VIII). Pedagogical — never imperative. */
export const TRADEABILITY_HINT_FR: Record<TradeabilityFlag, string> = {
  tradeable: "Toutes les conditions structurelles sont remplies pour un setup NY 13h-20h.",
  no_setup:
    "La conviction probabiliste est trop faible pour déclencher une lecture exploitable — verdict en mode dormant.",
  holiday:
    "Le marché actions US est fermé ou en volume réduit ; même le forex et l'or voient une volatilité dégradée. Discipline trader = pas de prise de position aujourd'hui.",
  event_freeze:
    "Une donnée économique à fort impact est prévue dans les 2 prochaines heures. Discipline = attendre la publication + réaction avant tout position.",
  low_volatility:
    "La volatilité moyenne sur cette heure-UTC (fenêtre glissante 30 jours) est sous le seuil structurel. Le momentum NY est statistiquement improbable.",
  range:
    "Les 3 dernières bougies daily sont en consolidation (corps faible) — environnement range-bound où les manipulations à l'open dominent les momentum.",
};

/** Visual tone token per TradeabilityFlag. `tradeable` reste invisible
 *  (pas de chrome), tous les autres dégradent en `text-muted` pour
 *  signaler honest disclosure sans drama. */
export const TRADEABILITY_TONE: Record<TradeabilityFlag, string> = {
  tradeable: "",
  no_setup: "text-[var(--color-text-muted)]",
  holiday: "text-[var(--color-text-muted)]",
  event_freeze: "text-[var(--color-text-muted)]",
  low_volatility: "text-[var(--color-text-muted)]",
  range: "text-[var(--color-text-muted)]",
};

/** Whether the trader should consider acting on the verdict today. Pure
 *  function — RSC-safe, no React, no I/O. */
export function isTradeable(verdict: SessionVerdict): boolean {
  return verdict.tradeability === "tradeable";
}

/* ──────────────────────── PURE HELPERS (continued) ─────────────── */

/** Format the verdict's window stamps into a single Paris-time line :
 *  "fenêtre opératoire : 13h00 → 20h00 Paris". Pure function. */
export function formatWindow(verdict: SessionVerdict): string {
  const open = new Date(verdict.ne_pas_actionner_avant_paris);
  const close = new Date(verdict.couper_au_plus_tard_paris);
  const fmt = new Intl.DateTimeFormat("fr-FR", {
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "Europe/Paris",
  });
  return `fenêtre opératoire : ${fmt.format(open)} → ${fmt.format(close)} Paris`;
}
