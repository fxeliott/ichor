/**
 * NarrativeBlocks — three sister panels rendering the narrative-shape
 * sub-objects of a SessionCard : mechanisms, invalidations, catalysts.
 *
 * Backend stores these as JSONB lists of structured objects ; in the
 * absence of a strict schema (the orchestrator emits Pass-2 dictionaries
 * straight from the LLM JSON) we render defensively :
 *
 *   - If item is a string → render as bullet
 *   - If item is an object → render the most-likely text field
 *     (description / text / why / condition / event), then optional
 *     metadata (probability, weight, when_utc) as muted suffixes.
 *
 * Rule 4 frontend ungeled this round (r65) — first consumer of these
 * three Pass-2 surfaces in the new premium briefing route.
 */

"use client";

import { m } from "motion/react";
import { type ReactNode } from "react";

interface NarrativeBlockProps {
  title: string;
  blurb: string;
  items: unknown;
  emptyLabel: string;
  accent: "bull" | "bear" | "neutral" | "warn";
  delay?: number;
}

const ACCENT_BORDER: Record<NarrativeBlockProps["accent"], string> = {
  bull: "border-l-[--color-bull]",
  bear: "border-l-[--color-bear]",
  neutral: "border-l-[--color-accent-cobalt]",
  warn: "border-l-[--color-warn]",
};

function extractText(item: unknown): { primary: string; meta: string | null } {
  if (typeof item === "string") return { primary: item, meta: null };
  if (item === null || typeof item !== "object") {
    return { primary: String(item), meta: null };
  }
  const rec = item as Record<string, unknown>;
  // Probe common field names in priority order.
  const primary =
    (rec.description as string) ??
    (rec.text as string) ??
    (rec.why as string) ??
    (rec.condition as string) ??
    (rec.event as string) ??
    (rec.label as string) ??
    JSON.stringify(rec);

  const metaParts: string[] = [];
  if (typeof rec.probability === "number") {
    metaParts.push(`p=${(rec.probability * 100).toFixed(0)}%`);
  }
  if (typeof rec.weight === "number") {
    metaParts.push(`w=${rec.weight.toFixed(2)}`);
  }
  if (typeof rec.when_utc === "string") {
    metaParts.push(rec.when_utc);
  } else if (typeof rec.when === "string") {
    metaParts.push(rec.when);
  }
  if (typeof rec.source === "string") {
    metaParts.push(rec.source);
  }

  return { primary, meta: metaParts.length > 0 ? metaParts.join(" · ") : null };
}

function NarrativeBlock({
  title,
  blurb,
  items,
  emptyLabel,
  accent,
  delay = 0,
}: NarrativeBlockProps): ReactNode {
  const list = Array.isArray(items) ? items : [];

  return (
    <m.section
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, delay }}
      className="overflow-hidden rounded-2xl border border-[--color-border-subtle] bg-[--color-bg-surface]/40 backdrop-blur-xl"
    >
      <header className="border-b border-[--color-border-subtle] px-6 py-4">
        <h3 className="font-serif text-lg text-[--color-text-primary]">{title}</h3>
        <p className="mt-1 text-xs text-[--color-text-muted]">{blurb}</p>
      </header>
      {list.length === 0 ? (
        <div className="px-6 py-6 text-sm italic text-[--color-text-muted]">{emptyLabel}</div>
      ) : (
        <ul className="divide-y divide-[--color-border-subtle]/60">
          {list.map((item, i) => {
            const { primary, meta } = extractText(item);
            return (
              <li
                key={i}
                className={`border-l-2 ${ACCENT_BORDER[accent]} px-6 py-4 transition-colors hover:bg-[--color-bg-elevated]/40`}
              >
                <p className="text-sm leading-relaxed text-[--color-text-primary]">{primary}</p>
                {meta && (
                  <p className="mt-1.5 font-mono text-[10px] uppercase tracking-wider text-[--color-text-muted]">
                    {meta}
                  </p>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </m.section>
  );
}

interface NarrativeBlocksProps {
  mechanisms: unknown;
  invalidations: unknown;
  catalysts: unknown;
}

export function NarrativeBlocks({ mechanisms, invalidations, catalysts }: NarrativeBlocksProps) {
  return (
    <div className="grid gap-6 lg:grid-cols-3">
      <NarrativeBlock
        title="Mécanismes"
        blurb="Les chaînes de causalité Pass-2 — pourquoi le bias devrait se matérialiser."
        items={mechanisms}
        emptyLabel="No mechanism extracted from this card."
        accent="bull"
        delay={0}
      />
      <NarrativeBlock
        title="Invalidations"
        blurb="Conditions Pass-4 qui invalident la thèse — niveaux + événements à surveiller."
        items={invalidations}
        emptyLabel="No explicit invalidation listed (interpret as fully Tetlockable)."
        accent="warn"
        delay={0.08}
      />
      <NarrativeBlock
        title="Catalystes"
        blurb="Événements à venir Pass-2 qui peuvent accélérer ou freiner la thèse."
        items={catalysts}
        emptyLabel="No catalyst surfaced for this session."
        accent="neutral"
        delay={0.16}
      />
    </div>
  );
}
