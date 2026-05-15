/**
 * SentimentPanel — MyFXBook retail positioning + contrarian tilt.
 *
 * r69 — shape verified against REAL Hetzner /v1/positioning (R59) :
 *   { generated_at, n_pairs, entries:[{ pair, long_pct, short_pct,
 *     ..., dominant_side, intensity, contrarian_tilt, note }] }
 *
 * Serves Eliot's "ce que les gens font" (retail crowd) + the contrarian
 * read ("la foule est à contre-sens aux extrêmes"). For the briefing
 * asset we surface its own pair prominently if covered ; the rest of
 * the complex is a compact strip. MyFXBook is FX/metals only — for
 * SPX500/NAS100 we render an explicit "N/A indices" state (honest
 * coverage boundary, not a silent empty).
 *
 * ADR-017 : positioning + contrarian *tilt* is sentiment context, NOT
 * a trade signal. Vocabulary stays "biais contrarian", never BUY/SELL.
 */

"use client";

import { m } from "motion/react";

import type { PositioningEntry } from "@/lib/api";

// Ichor priority asset → MyFXBook pair label (no underscore).
const ASSET_TO_MYFXBOOK: Record<string, string | null> = {
  EUR_USD: "EURUSD",
  GBP_USD: "GBPUSD",
  XAU_USD: "XAUUSD",
  SPX500_USD: null, // index — not covered by MyFXBook
  NAS100_USD: null, // index — not covered by MyFXBook
};

const TILT_TONE: Record<PositioningEntry["contrarian_tilt"], string> = {
  bullish: "text-[--color-bull]",
  bearish: "text-[--color-bear]",
  neutral: "text-[--color-neutral]",
};

const TILT_GLYPH: Record<PositioningEntry["contrarian_tilt"], string> = {
  bullish: "▲ +",
  bearish: "▼ −",
  neutral: "◆ ±",
};

function SplitBar({ longPct, shortPct }: { longPct: number; shortPct: number }) {
  return (
    <div className="flex h-2.5 w-full overflow-hidden rounded-full bg-[--color-bg-base]">
      <m.div
        initial={{ width: 0 }}
        animate={{ width: `${longPct}%` }}
        transition={{ duration: 0.6, ease: "easeOut", delay: 0.2 }}
        className="h-full bg-[--color-bull]"
      />
      <m.div
        initial={{ width: 0 }}
        animate={{ width: `${shortPct}%` }}
        transition={{ duration: 0.6, ease: "easeOut", delay: 0.2 }}
        className="h-full bg-[--color-bear]"
      />
    </div>
  );
}

interface SentimentPanelProps {
  entries: PositioningEntry[];
  asset: string;
}

export function SentimentPanel({ entries, asset }: SentimentPanelProps) {
  const myfxPair = ASSET_TO_MYFXBOOK[asset];
  const isIndex = myfxPair === null && asset in ASSET_TO_MYFXBOOK;

  const focus = myfxPair != null ? (entries.find((e) => e.pair === myfxPair) ?? null) : null;
  const others = entries
    .filter((e) => e.pair !== myfxPair)
    .sort((a, b) => Math.max(b.long_pct, b.short_pct) - Math.max(a.long_pct, a.short_pct));

  return (
    <m.section
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className="overflow-hidden rounded-2xl border border-[--color-border-subtle] bg-[--color-bg-surface]/40 backdrop-blur-xl"
    >
      <header className="border-b border-[--color-border-subtle] px-6 py-4">
        <h3 className="font-serif text-lg text-[--color-text-primary]">Positionnement retail</h3>
        <p className="mt-1 text-xs text-[--color-text-muted]">
          MyFXBook · la foule retail est structurellement à contre-sens aux extrêmes (biais
          contrarian) · vert long / rouge short
        </p>
      </header>

      {isIndex && (
        <div className="border-b border-[--color-border-subtle] px-6 py-4 text-sm text-[--color-text-muted]">
          <span className="font-medium text-[--color-text-secondary]">
            {asset.replace("_", "/")}
          </span>{" "}
          — MyFXBook ne couvre pas les indices actions (FX / métaux uniquement). Pas de donnée de
          positionnement retail pour cet actif.
        </div>
      )}

      {focus && (
        <div className="border-b border-[--color-border-subtle] bg-[--color-bg-elevated]/30 px-6 py-5">
          <div className="flex items-baseline justify-between gap-4">
            <span className="font-mono text-sm text-[--color-text-secondary]">
              {asset.replace("_", "/")}
            </span>
            <span className={`font-serif text-lg ${TILT_TONE[focus.contrarian_tilt]}`}>
              {TILT_GLYPH[focus.contrarian_tilt]} contrarian {focus.contrarian_tilt}
            </span>
          </div>
          <div className="mt-3">
            <div className="mb-1.5 flex justify-between font-mono text-xs tabular-nums">
              <span className="text-[--color-bull]">{focus.long_pct.toFixed(0)}% long</span>
              <span className="text-[10px] uppercase tracking-wider text-[--color-text-muted]">
                {focus.intensity}
              </span>
              <span className="text-[--color-bear]">{focus.short_pct.toFixed(0)}% short</span>
            </div>
            <SplitBar longPct={focus.long_pct} shortPct={focus.short_pct} />
          </div>
          <p className="mt-3 text-xs leading-relaxed text-[--color-text-secondary]">{focus.note}</p>
        </div>
      )}

      {others.length > 0 && (
        <ul className="divide-y divide-[--color-border-subtle]/60">
          {others.map((e, i) => (
            <m.li
              key={e.pair}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ duration: 0.2, delay: i * 0.05 }}
              className="px-6 py-3"
            >
              <div className="flex items-center gap-4">
                <span className="w-16 shrink-0 font-mono text-sm text-[--color-text-secondary]">
                  {e.pair}
                </span>
                <div className="flex-1">
                  <SplitBar longPct={e.long_pct} shortPct={e.short_pct} />
                </div>
                <span className="w-28 shrink-0 text-right font-mono text-xs tabular-nums text-[--color-text-muted]">
                  {e.long_pct.toFixed(0)}/{e.short_pct.toFixed(0)}
                </span>
                <span
                  className={`w-16 shrink-0 text-right text-xs ${TILT_TONE[e.contrarian_tilt]}`}
                  title={e.note}
                >
                  {e.contrarian_tilt === "neutral" ? "—" : TILT_GLYPH[e.contrarian_tilt]}
                </span>
              </div>
            </m.li>
          ))}
        </ul>
      )}

      {!focus && !isIndex && others.length === 0 && (
        <div className="px-6 py-6 text-sm italic text-[--color-text-muted]">
          Positionnement retail indisponible (collecteur MyFXBook non encore exécuté).
        </div>
      )}
    </m.section>
  );
}
