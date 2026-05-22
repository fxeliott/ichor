/**
 * NewsPanel — recent news feed with tone, from /v1/news.
 *
 * r69 — shape verified against REAL Hetzner data (R59) : /v1/news
 * returns a BARE list[NewsItem] (not enveloped) :
 *   { id, fetched_at, source, source_kind, title, summary, url,
 *     published_at, tone_label, tone_score }
 *
 * Serves Eliot's "les news" + "ce que les gens en pensent" (tone is a
 * sentiment proxy). Items grouped/sorted newest-first, source_kind
 * badge (central_bank highlighted — Fed/ECB pressers move markets),
 * tone-coded left accent (positive=bull, negative=bear, neutral). Title
 * links out (new tab, rel=noopener). ADR-017 : news context, no signal.
 */

"use client";

import { m } from "motion/react";

import type { NewsFilterMeta, NewsItem } from "@/lib/api";

const KIND_LABEL: Record<string, string> = {
  central_bank: "BANQUE CENTRALE",
  news: "PRESSE",
  regulator: "RÉGULATEUR",
  social: "SOCIAL",
  academic: "ACADÉMIQUE",
};

function toneTone(label: string | null, score: number | null): "bull" | "bear" | "neutral" {
  if (label) {
    const l = label.toLowerCase();
    if (l.includes("pos") || l === "positive") return "bull";
    if (l.includes("neg") || l === "negative") return "bear";
  }
  if (typeof score === "number") {
    if (score > 0.15) return "bull";
    if (score < -0.15) return "bear";
  }
  return "neutral";
}

const TONE_BORDER: Record<"bull" | "bear" | "neutral", string> = {
  bull: "border-l-[var(--color-bull)]",
  bear: "border-l-[var(--color-bear)]",
  neutral: "border-l-[var(--color-border-default)]",
};

function relTime(iso: string): string {
  const then = new Date(iso).getTime();
  const min = Math.floor((Date.now() - then) / 60000);
  if (min < 1) return "à l'instant";
  if (min < 60) return `il y a ${min} min`;
  const h = Math.floor(min / 60);
  if (h < 24) return `il y a ${h} h`;
  return `il y a ${Math.floor(h / 24)} j`;
}

/**
 * r138 — calibrated disclosure of the per-asset news filter state
 * (lesson #11). Maps the backend `NewsFilterMeta` envelope to a short,
 * honest French label rendered in the panel header. The four states
 * are mutually-exclusive and never inflate (e.g. we never claim
 * "filtré" when the scarce-fallback fired).
 */
function filterLabel(
  filter: NewsFilterMeta | null,
  fallbackAsset: string | null,
): { line: string; tone: "ok" | "scarce" | "global" | "none" } {
  if (!filter) {
    // No asset was requested (legacy global feed) — honest absence-of-filter.
    return { line: "Flux global · tous actifs", tone: "global" };
  }
  if (!filter.known_asset) {
    return {
      line: `Actif "${filter.asset}" hors carte de mots-clés · flux global`,
      tone: "global",
    };
  }
  if (filter.applied) {
    return {
      line: `Filtré · ${filter.matched} item${filter.matched > 1 ? "s" : ""} liés à ${filter.asset}`,
      tone: "ok",
    };
  }
  // applied=false & known_asset=true → scarce fallback fired.
  // r138 trader YELLOW #4 anti-emergent-directional-read : the prior copy
  // "Flux global (aucun item spécifique à EUR)" could read under time
  // pressure as "no news = no catalyst" — a directional leak through
  // structural-honesty (ADR-017 boundary). Anchor with "pas un signal" the
  // same way <MacroSurprisePanel> r136 footer neutralises absence reads.
  const matchedTxt =
    filter.matched === 0 ? "aucun item" : `${filter.matched} item${filter.matched > 1 ? "s" : ""}`;
  const assetLabel = filter.asset ?? fallbackAsset ?? "l'actif";
  return {
    line: `Flux global affiché — ${matchedTxt} spécifique${filter.matched > 1 ? "s" : ""} à ${assetLabel} sur la fenêtre (seuil ${filter.min_required} — peut refléter un creux d'actualité, pas un signal)`,
    tone: "scarce",
  };
}

export function NewsPanel({
  news,
  filter = null,
  asset = null,
}: {
  news: NewsItem[];
  /** r138 — `null` for back-compat pre-r138 callers (no asset filter). */
  filter?: NewsFilterMeta | null;
  /** r138 — informational ; used when filter is null but caller wants
   *  to label the panel with the asset context anyway. */
  asset?: string | null;
}) {
  const disclosure = filterLabel(filter, asset);
  if (!news || news.length === 0) {
    return (
      <div className="rounded-2xl border border-[var(--color-border-subtle)] bg-[var(--color-bg-surface)]/40 p-8 text-center backdrop-blur-xl">
        <p className="font-serif text-lg text-[var(--color-text-secondary)]">
          Pas d&apos;actualité récente.
        </p>
        <p className="mt-2 text-xs text-[var(--color-text-muted)]">{disclosure.line}.</p>
      </div>
    );
  }

  const sorted = [...news].sort(
    (a, b) =>
      new Date(b.published_at || b.fetched_at).getTime() -
      new Date(a.published_at || a.fetched_at).getTime(),
  );

  return (
    <m.section
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className="overflow-hidden rounded-2xl border border-[var(--color-border-subtle)] bg-[var(--color-bg-surface)]/40 backdrop-blur-xl"
    >
      <header className="border-b border-[var(--color-border-subtle)] px-6 py-4">
        <h3 className="font-serif text-lg text-[var(--color-text-primary)]">Actualités</h3>
        <p
          className={`mt-1 text-xs ${
            disclosure.tone === "ok"
              ? "text-[var(--color-text-secondary)]"
              : disclosure.tone === "scarce"
                ? "text-[var(--color-text-muted)]"
                : "text-[var(--color-text-muted)]"
          }`}
        >
          {disclosure.line} · banques centrales surlignées · accent = tonalité
        </p>
      </header>

      <ul className="divide-y divide-[var(--color-border-subtle)]/60">
        {sorted.map((n, i) => {
          const tone = toneTone(n.tone_label, n.tone_score);
          const isCB = n.source_kind === "central_bank";
          return (
            <m.li
              key={n.id}
              initial={{ opacity: 0, x: -6 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ duration: 0.22, delay: Math.min(i * 0.03, 0.4) }}
              className={`border-l-2 ${TONE_BORDER[tone]} px-6 py-4 transition-colors hover:bg-[var(--color-bg-elevated)]/40 ${
                isCB ? "bg-[var(--color-bg-elevated)]/20" : ""
              }`}
            >
              <div className="flex items-baseline gap-2">
                <span
                  className={`font-mono text-[10px] uppercase tracking-wider ${
                    isCB
                      ? "text-[var(--color-accent-cobalt-bright)]"
                      : "text-[var(--color-text-muted)]"
                  }`}
                >
                  {KIND_LABEL[n.source_kind] ?? n.source_kind}
                </span>
                <span className="font-mono text-[10px] text-[var(--color-text-muted)]">
                  {n.source} · {relTime(n.published_at || n.fetched_at)}
                </span>
              </div>
              <a
                href={n.url}
                target="_blank"
                rel="noopener noreferrer"
                className="mt-1 block text-sm font-medium leading-relaxed text-[var(--color-text-primary)] hover:text-[var(--color-accent-cobalt-bright)]"
              >
                {n.title}
              </a>
              {n.summary && n.summary !== n.title && (
                <p className="mt-1 text-xs leading-relaxed text-[var(--color-text-secondary)]">
                  {n.summary.length > 220 ? `${n.summary.slice(0, 220)}…` : n.summary}
                </p>
              )}
            </m.li>
          );
        })}
      </ul>
    </m.section>
  );
}
