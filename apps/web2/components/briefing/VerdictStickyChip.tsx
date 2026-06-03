"use client";

/**
 * VerdictStickyChip — keeps the day's verdict DOMINANT while reading the
 * deep-dive. The apex `<SessionVerdictPanel>` (section A) is the primary read,
 * but the briefing is a long scroll — once the apex leaves the viewport the
 * trader loses the one number that matters. This pinned chip slides in the
 * moment the verdict section scrolls out of view and shows, at a glance :
 *
 *     [glyph] EUR/USD · Hausse · 72 %        (click → scroll back to verdict)
 *
 * Data precedence : the canonical `SessionVerdict` (same source as the apex
 * panel) when present, else the deterministic `SessionCard` bias/conviction
 * fallback (mirror of the apex's own fallback). Renders nothing when neither
 * exists. The chip is a *positional mirror* of the SSR verdict — the apex
 * panel owns the 60 s live-poll, so the chip stays a lightweight reflection
 * (no second poller).
 *
 * ADR-017 : re-expresses the verdict's direction + conviction as navigation
 * chrome, never an order. Voie D : pure presentational, zero LLM.
 */

import { m } from "motion/react";
import { useEffect, useState } from "react";

import type { SessionCard, SessionVerdict } from "@/lib/api";
import { DIRECTION_FR, DIRECTION_GLYPH } from "@/lib/sessionVerdict";

interface Props {
  verdict: SessionVerdict | null;
  card: SessionCard | null;
  asset: string;
}

type Dir = "up" | "down" | "neutral";

/** Map the card's long/short/neutral bias onto the verdict's up/down/neutral
 *  vocabulary so the chip can share the sessionVerdict.ts SSOT maps. */
const CARD_BIAS_TO_DIR: Record<string, Dir> = {
  long: "up",
  short: "down",
  neutral: "neutral",
};

const DIR_TONE: Record<Dir, string> = {
  up: "var(--color-bull)",
  down: "var(--color-bear)",
  neutral: "var(--color-neutral)",
};

export function VerdictStickyChip({ verdict, card, asset }: Props) {
  const [pastVerdict, setPastVerdict] = useState(false);

  // Show the chip only once the verdict READOUT has scrolled above the
  // viewport (the trader is reading the rest of the briefing). A zero-height
  // sentinel sits right after the apex panel in the page; the chip appears
  // once the sentinel's top crosses above the fold.
  //
  // NB a 0-height sentinel never reports `isIntersecting:true`, so an
  // IntersectionObserver (which only fires on isIntersecting *transitions*)
  // can silently miss an instant/fast scroll that jumps the sentinel from
  // below-fold straight to above-fold (both states report false). A
  // rAF-throttled scroll/resize listener reading the rect top is robust to
  // both fast jumps and smooth scrolling, at a negligible cost.
  useEffect(() => {
    const target = document.getElementById("verdict-sentinel");
    if (!target) return;
    let raf = 0;
    const measure = () => {
      raf = 0;
      setPastVerdict(target.getBoundingClientRect().top < 0);
    };
    const onScroll = () => {
      if (raf === 0) raf = requestAnimationFrame(measure);
    };
    measure(); // initial state
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll, { passive: true });
    // Late-loading content (sparklines, charts, polled panels) shifts the
    // sentinel AFTER the last scroll event — without this the visibility would
    // go stale until the next scroll (witnessed on prod mobile). A
    // ResizeObserver on document.body re-measures whenever the content height
    // changes (NOT documentElement — <html> stays viewport-sized and never
    // fires on content growth), so the chip self-corrects while stationary.
    const ro = new ResizeObserver(onScroll);
    ro.observe(document.body);
    return () => {
      if (raf) cancelAnimationFrame(raf);
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
      ro.disconnect();
    };
  }, []);

  // Resolve the display values — verdict first, card fallback.
  let dir: Dir | null = null;
  let convictionPct: number | null = null;
  let label = "";
  if (verdict) {
    dir = (verdict.direction as Dir) ?? "neutral";
    convictionPct = verdict.conviction_pct;
    label = DIRECTION_FR[verdict.direction] ?? verdict.direction;
  } else if (card) {
    dir = CARD_BIAS_TO_DIR[card.bias_direction] ?? "neutral";
    convictionPct = card.conviction_pct;
    label = DIRECTION_FR[dir] ?? dir;
  }

  if (dir === null || convictionPct === null) return null;

  const tone = DIR_TONE[dir];
  const glyph = DIRECTION_GLYPH[dir] ?? "◆";
  const pair = asset.replace("_", "/");
  const pct = Math.min(convictionPct, 95);

  const onClick = () => {
    const el = document.getElementById("verdict");
    if (!el) return;
    // Re-open the section if collapsed, then scroll (BriefingSection listens
    // for hashchange → opens itself).
    if (window.location.hash !== "#verdict") window.location.hash = "#verdict";
    el.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  return (
    <m.button
      type="button"
      onClick={onClick}
      initial={false}
      animate={
        pastVerdict
          ? { opacity: 1, y: 0, pointerEvents: "auto" }
          : { opacity: 0, y: 24, pointerEvents: "none" }
      }
      transition={{ type: "spring", stiffness: 320, damping: 28 }}
      aria-hidden={!pastVerdict}
      aria-label={`Verdict ${pair} : ${label}, conviction ${convictionPct.toFixed(0)} %. Cliquer pour revenir au verdict.`}
      className="group fixed bottom-[max(1.25rem,env(safe-area-inset-bottom))] right-4 z-[var(--z-sticky)] flex items-center gap-3 rounded-full border border-[var(--glass-border)] bg-[var(--glass-bg-strong)] py-2 pl-3 pr-4 text-left shadow-[var(--glow-card)] backdrop-blur-xl transition-colors hover:border-[var(--glass-border-hover)] md:right-6"
      style={{ boxShadow: "var(--glow-card)" }}
    >
      {/* tone-coloured direction glyph in a soft halo */}
      <span
        aria-hidden
        className="grid h-8 w-8 shrink-0 place-items-center rounded-full text-lg font-light leading-none"
        style={{
          color: tone,
          background: `color-mix(in oklab, ${tone} 16%, transparent)`,
        }}
      >
        {glyph}
      </span>
      <span className="flex flex-col leading-tight">
        <span className="text-[11px] uppercase tracking-wide text-[var(--color-text-muted)]">
          {pair} · verdict
        </span>
        <span className="flex items-baseline gap-1.5">
          <span className="text-sm font-medium" style={{ color: tone }}>
            {label}
          </span>
          <span className="font-mono text-sm tabular-nums text-[var(--color-text-primary)]">
            {convictionPct.toFixed(0)}%
          </span>
        </span>
      </span>
      {/* thin tone conviction bar */}
      <span
        aria-hidden
        className="ml-1 hidden h-1 w-12 overflow-hidden rounded-full bg-[var(--color-bg-base)] sm:block"
      >
        <span
          className="block h-full rounded-full"
          style={{ width: `${pct}%`, background: tone }}
        />
      </span>
    </m.button>
  );
}
