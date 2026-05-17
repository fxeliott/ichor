/**
 * NarrativeBlocks — three sister panels rendering the narrative-shape
 * sub-objects of a SessionCard : mechanisms, invalidations, catalysts.
 *
 * r66 — shapes verified against REAL Hetzner Pass-2 output (not guessed) :
 *
 *   mechanisms[]   : { claim: string, sources: string[] }
 *   invalidations[]: { source: string, condition: string, threshold: string }
 *   catalysts[]    : { time: string, event: string, expected_impact: string }
 *
 * Pre-r66 this component used a generic `extractText` field-probe that
 * did NOT match the real schema (`claim` / `expected_impact` /
 * `threshold` were all missed → raw-JSON fallback render). r66 replaces
 * the guess with three shape-aware renderers. Each block still degrades
 * gracefully to a string / JSON dump for unknown shapes (defensive —
 * the orchestrator emits Pass-2 LLM JSON, which can drift).
 *
 * R59 doctrine : structure that "works" against an empty test DB is not
 * proof — only real prod data is. This rewrite is that proof applied.
 */

"use client";

import { m } from "motion/react";
import { type ReactNode } from "react";

// ── Real Pass-2 shapes (verified r66 against /v1/sessions/EUR_USD prod) ──

interface Mechanism {
  claim: string;
  sources?: string[];
}

interface Invalidation {
  source?: string;
  condition: string;
  threshold?: string;
}

interface Catalyst {
  time?: string;
  event: string;
  expected_impact?: string;
}

function asArray<T>(items: unknown): T[] {
  return Array.isArray(items) ? (items as T[]) : [];
}

function shortSource(s: string): string {
  // "FRED:DGS10" → "DGS10" ; "polymarket:will-the-fed-..." → "polymarket"
  if (s.includes(":")) {
    const [prefix, rest] = s.split(":", 2);
    if (prefix === "polymarket" || prefix === "polygon") return prefix;
    return rest ?? s;
  }
  return s;
}

function fmtTime(iso: string): string {
  try {
    const d = new Date(iso);
    return (
      d.toLocaleString("fr-FR", {
        day: "2-digit",
        month: "short",
        hour: "2-digit",
        minute: "2-digit",
        timeZone: "UTC",
      }) + " UTC"
    );
  } catch {
    return iso;
  }
}

function PanelShell({
  title,
  blurb,
  delay,
  count,
  children,
}: {
  title: string;
  blurb: string;
  delay: number;
  count: number;
  children: ReactNode;
}) {
  return (
    <m.section
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, delay }}
      className="overflow-hidden rounded-2xl border border-[--color-border-subtle] bg-[--color-bg-surface]/40 backdrop-blur-xl"
    >
      <header className="border-b border-[--color-border-subtle] px-6 py-4">
        <div className="flex items-baseline justify-between gap-4">
          <h3 className="font-serif text-lg text-[--color-text-primary]">{title}</h3>
          <span className="text-[10px] uppercase tracking-widest text-[--color-text-muted]">
            {count} {count === 1 ? "item" : "items"}
          </span>
        </div>
        <p className="mt-1 text-xs text-[--color-text-muted]">{blurb}</p>
      </header>
      {children}
    </m.section>
  );
}

const ACCENT_BORDER = {
  bull: "border-l-[--color-bull]",
  warn: "border-l-[--color-warn]",
  neutral: "border-l-[--color-accent-cobalt]",
} as const;

function EmptyRow({ label }: { label: string }) {
  return <div className="px-6 py-6 text-sm italic text-[--color-text-muted]">{label}</div>;
}

interface NarrativeBlocksProps {
  mechanisms: unknown;
  invalidations: unknown;
  catalysts: unknown;
}

export function NarrativeBlocks({ mechanisms, invalidations, catalysts }: NarrativeBlocksProps) {
  const mechs = asArray<Mechanism>(mechanisms);
  const invals = asArray<Invalidation>(invalidations);
  const cats = asArray<Catalyst>(catalysts);

  return (
    <div className="grid gap-6 lg:grid-cols-3">
      {/* ── Mécanismes : {claim, sources[]} ── */}
      <PanelShell
        title="Mécanismes"
        blurb="Chaînes de causalité Pass-2 — pourquoi le bias devrait se matérialiser."
        delay={0}
        count={mechs.length}
      >
        {mechs.length === 0 ? (
          <EmptyRow label="No mechanism extracted from this card." />
        ) : (
          <ul className="divide-y divide-[--color-border-subtle]/60">
            {mechs.map((mech, i) => (
              <li
                key={i}
                className={`border-l-2 ${ACCENT_BORDER.bull} px-6 py-4 transition-colors hover:bg-[--color-bg-elevated]/40`}
              >
                <p className="text-sm leading-relaxed text-[--color-text-primary]">
                  {mech.claim ?? JSON.stringify(mech)}
                </p>
                {mech.sources && mech.sources.length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {mech.sources.map((s, si) => (
                      <span
                        key={si}
                        className="rounded-full border border-[--color-border-default] px-2 py-0.5 font-mono text-[10px] text-[--color-text-muted]"
                        title={s}
                      >
                        {shortSource(s)}
                      </span>
                    ))}
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
      </PanelShell>

      {/* ── Invalidations : {source, condition, threshold} ── */}
      <PanelShell
        title="Invalidations"
        blurb="Conditions Pass-4 qui cassent la thèse — niveaux + événements à surveiller."
        delay={0.08}
        count={invals.length}
      >
        {invals.length === 0 ? (
          <EmptyRow label="No explicit invalidation (interpret as fully Tetlockable)." />
        ) : (
          <ul className="divide-y divide-[--color-border-subtle]/60">
            {invals.map((inv, i) => (
              <li
                key={i}
                className={`border-l-2 ${ACCENT_BORDER.warn} px-6 py-4 transition-colors hover:bg-[--color-bg-elevated]/40`}
              >
                <div className="flex items-start justify-between gap-4">
                  <p className="text-sm leading-relaxed text-[--color-text-primary]">
                    {inv.condition ?? JSON.stringify(inv)}
                  </p>
                  {inv.threshold && (
                    <span className="shrink-0 rounded-md bg-[--color-warn]/10 px-2 py-1 font-mono text-sm font-medium tabular-nums text-[--color-warn]">
                      {inv.threshold}
                    </span>
                  )}
                </div>
                {inv.source && (
                  <p className="mt-2 font-mono text-[10px] uppercase tracking-wider text-[--color-text-muted]">
                    {shortSource(inv.source)}
                  </p>
                )}
              </li>
            ))}
          </ul>
        )}
      </PanelShell>

      {/* ── Catalystes : {time, event, expected_impact} ── */}
      <PanelShell
        title="Catalystes"
        blurb="Événements à venir Pass-2 — ce qui peut accélérer ou freiner la thèse."
        delay={0.16}
        count={cats.length}
      >
        {cats.length === 0 ? (
          <EmptyRow label="No catalyst surfaced for this session." />
        ) : (
          <ul className="divide-y divide-[--color-border-subtle]/60">
            {cats.map((cat, i) => (
              <li
                key={i}
                className={`border-l-2 ${ACCENT_BORDER.neutral} px-6 py-4 transition-colors hover:bg-[--color-bg-elevated]/40`}
              >
                {cat.time && (
                  <p className="font-mono text-[10px] uppercase tracking-wider text-[--color-accent-cobalt-bright]">
                    {fmtTime(cat.time)}
                  </p>
                )}
                <p className="mt-1 text-sm font-medium leading-relaxed text-[--color-text-primary]">
                  {cat.event ?? JSON.stringify(cat)}
                </p>
                {cat.expected_impact && (
                  <p className="mt-1.5 text-xs leading-relaxed text-[--color-text-secondary]">
                    {cat.expected_impact}
                  </p>
                )}
              </li>
            ))}
          </ul>
        )}
      </PanelShell>
    </div>
  );
}
