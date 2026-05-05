"use client";

/**
 * BiasOpportunitiesGrid — replaces the 3 hardcoded mock SessionCard
 * on the home page with the real top sessions from /v1/today.
 *
 * The /v1/today endpoint already aggregates the top-N session cards
 * sorted by conviction × regime fit (+ a calendar context). We map
 * each `top_sessions[i]` into a compact "opportunity" cell with :
 *   - asset + bias direction
 *   - conviction % progress bar (animated on update)
 *   - magnitude pips range
 *   - regime quadrant tag
 *   - "open card →" link to /sessions/{asset}
 *
 * On API offline, renders a polite empty-state.
 *
 * Animations : list items fade-in stagger, conviction bar fills
 * smoothly. Respects prefers-reduced-motion.
 */

import { motion, useReducedMotion } from "motion/react";
import Link from "next/link";

interface TodayTopSession {
  asset: string;
  bias_direction: "long" | "short" | "neutral";
  conviction_pct: number;
  magnitude_pips_low: number | null;
  magnitude_pips_high: number | null;
  regime_quadrant: string | null;
  generated_at: string;
}

interface TodayOut {
  generated_at: string;
  top_sessions: TodayTopSession[];
  n_session_cards: number;
}

function biasColor(d: TodayTopSession["bias_direction"]): string {
  if (d === "long") return "var(--color-bull)";
  if (d === "short") return "var(--color-bear)";
  return "var(--color-text-muted)";
}

function biasGlyph(d: TodayTopSession["bias_direction"]): string {
  if (d === "long") return "▲";
  if (d === "short") return "▼";
  return "●";
}

function relTime(iso: string): string {
  const d = Date.now() - new Date(iso).getTime();
  const m = Math.floor(d / 60_000);
  if (m < 1) return "à l'instant";
  if (m < 60) return `il y a ${m}min`;
  const h = Math.floor(m / 60);
  if (h < 24) return `il y a ${h}h`;
  return `il y a ${Math.floor(h / 24)}j`;
}

export function BiasOpportunitiesGrid({ data }: { data: TodayOut | null }) {
  const reduced = useReducedMotion();

  if (!data || data.top_sessions.length === 0) {
    return (
      <div className="rounded-xl border border-dashed border-[var(--color-border-default)] bg-[var(--color-bg-surface)] px-6 py-12 text-center text-sm text-[var(--color-text-muted)]">
        Aucune session card disponible. Le brain regenère à 07:30 (pré-Londres) et 13:30 (pré-NY) Paris.
      </div>
    );
  }

  return (
    <div className="grid gap-4 lg:grid-cols-2 xl:grid-cols-3">
      {data.top_sessions.slice(0, 6).map((s, i) => (
        <motion.div
          key={`${s.asset}-${s.generated_at}`}
          initial={reduced ? false : { y: 12, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          transition={{ delay: reduced ? 0 : i * 0.07, duration: 0.32 }}
        >
          <OpportunityCard session={s} />
        </motion.div>
      ))}
    </div>
  );
}

function OpportunityCard({ session: s }: { session: TodayTopSession }) {
  const reduced = useReducedMotion();
  const color = biasColor(s.bias_direction);
  const glyph = biasGlyph(s.bias_direction);
  const conviction = Math.max(0, Math.min(100, s.conviction_pct));

  return (
    <Link
      href={`/sessions/${s.asset}`}
      className="group block rounded-xl border border-[var(--color-border-default)] bg-[var(--color-bg-surface)] p-5 shadow-[var(--shadow-md)] transition hover:border-[var(--color-border-strong,_rgba(255,255,255,0.2))] hover:shadow-[var(--shadow-lg,_0_8px_24px_rgba(0,0,0,0.18))]"
    >
      <header className="mb-3 flex items-start justify-between gap-3">
        <div>
          <p
            className="font-mono text-base font-semibold tracking-tight"
            style={{ color }}
          >
            <span className="mr-1.5" aria-hidden="true">{glyph}</span>
            {s.asset.replace("_", "/")}
          </p>
          <p className="font-mono text-[9px] uppercase tracking-widest text-[var(--color-text-muted)]">
            {s.regime_quadrant ?? "regime n/a"} · {relTime(s.generated_at)}
          </p>
        </div>
        <span
          className="rounded border px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-widest"
          style={{ color, borderColor: `${color}40` }}
        >
          {s.bias_direction}
        </span>
      </header>

      <div className="space-y-2">
        <div className="flex items-baseline justify-between font-mono text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]">
          <span>conviction</span>
          <span className="text-sm font-semibold tabular-nums" style={{ color }}>
            {conviction.toFixed(0)}%
          </span>
        </div>
        <div className="h-1.5 w-full overflow-hidden rounded-full bg-[var(--color-bg-elevated)]">
          <motion.div
            initial={reduced ? false : { width: 0 }}
            animate={{ width: `${conviction}%` }}
            transition={{ duration: reduced ? 0 : 0.8, ease: "easeOut" }}
            className="h-full rounded-full"
            style={{ backgroundColor: color }}
          />
        </div>

        {s.magnitude_pips_low !== null && s.magnitude_pips_high !== null ? (
          <p className="font-mono text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]">
            magnitude {s.magnitude_pips_low.toFixed(0)}–{s.magnitude_pips_high.toFixed(0)} pips
          </p>
        ) : null}
      </div>

      <p className="mt-4 inline-flex items-center gap-1 text-[10px] uppercase tracking-widest text-[var(--color-text-muted)] transition group-hover:text-[var(--color-text-primary)]">
        ouvrir card <span aria-hidden="true">→</span>
      </p>
    </Link>
  );
}
