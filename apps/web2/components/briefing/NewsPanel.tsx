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

import type { NewsItem } from "@/lib/api";

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
  bull: "border-l-[--color-bull]",
  bear: "border-l-[--color-bear]",
  neutral: "border-l-[--color-border-default]",
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

export function NewsPanel({ news }: { news: NewsItem[] }) {
  if (!news || news.length === 0) {
    return (
      <div className="rounded-2xl border border-[--color-border-subtle] bg-[--color-bg-surface]/40 p-8 text-center backdrop-blur-xl">
        <p className="font-serif text-lg text-[--color-text-secondary]">
          Pas d&apos;actualité récente.
        </p>
        <p className="mt-2 text-xs text-[--color-text-muted]">Flux vide ou source indisponible.</p>
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
      className="overflow-hidden rounded-2xl border border-[--color-border-subtle] bg-[--color-bg-surface]/40 backdrop-blur-xl"
    >
      <header className="border-b border-[--color-border-subtle] px-6 py-4">
        <h3 className="font-serif text-lg text-[--color-text-primary]">Actualités</h3>
        <p className="mt-1 text-xs text-[--color-text-muted]">
          Flux récent · banques centrales surlignées · accent = tonalité
        </p>
      </header>

      <ul className="divide-y divide-[--color-border-subtle]/60">
        {sorted.map((n, i) => {
          const tone = toneTone(n.tone_label, n.tone_score);
          const isCB = n.source_kind === "central_bank";
          return (
            <m.li
              key={n.id}
              initial={{ opacity: 0, x: -6 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ duration: 0.22, delay: Math.min(i * 0.03, 0.4) }}
              className={`border-l-2 ${TONE_BORDER[tone]} px-6 py-4 transition-colors hover:bg-[--color-bg-elevated]/40 ${
                isCB ? "bg-[--color-bg-elevated]/20" : ""
              }`}
            >
              <div className="flex items-baseline gap-2">
                <span
                  className={`font-mono text-[10px] uppercase tracking-wider ${
                    isCB ? "text-[--color-accent-cobalt-bright]" : "text-[--color-text-muted]"
                  }`}
                >
                  {KIND_LABEL[n.source_kind] ?? n.source_kind}
                </span>
                <span className="font-mono text-[10px] text-[--color-text-muted]">
                  {n.source} · {relTime(n.published_at || n.fetched_at)}
                </span>
              </div>
              <a
                href={n.url}
                target="_blank"
                rel="noopener noreferrer"
                className="mt-1 block text-sm font-medium leading-relaxed text-[--color-text-primary] hover:text-[--color-accent-cobalt-bright]"
              >
                {n.title}
              </a>
              {n.summary && n.summary !== n.title && (
                <p className="mt-1 text-xs leading-relaxed text-[--color-text-secondary]">
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
