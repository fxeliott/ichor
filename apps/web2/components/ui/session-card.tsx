// SessionCard — carte cœur du produit Ichor (lecture multidimensionnelle
// pré-session, cf docs/SPEC_V2_TRADER.md §8).
//
// NB ADR-017 / §7.8 : la carte ne rend AUCUN ordre — pas d'entry zone, SL,
// TP ni trail. L'ancien bloc « Trade plan » a été retiré (le trader fait son
// analyse technique lui-même ; Ichor n'enrichit que le contexte). Le niveau
// d'invalidation reste affiché de façon descriptive (« ce qui casserait la
// lecture »), jamais comme un stop-loss.
//
// Tout chiffré bias passe par <BiasIndicator> (redondance triple §14).

import { cn } from "@/lib/cn";
import { BiasIndicator } from "./bias-indicator";

type Bias = "bull" | "bear" | "neutral";

export interface Trigger {
  id: string;
  label: string;
  scheduledAt: string; // ISO
  importance?: "low" | "medium" | "high";
}

export interface CrossAssetItem {
  symbol: string;
  bias: Bias;
  value: number;
}

export interface Driver {
  factor: string;
  contribution: number; // -1..1
  evidence?: string;
}

export interface TradeSetup {
  entryLow: number;
  entryHigh: number;
  invalidationLevel: number;
  invalidationCondition: string;
  tpRR3: number;
  tpRR15: number;
  partialScheme: string; // e.g. "90% @ RR3 · 10% trail RR15+"
}

export interface SessionCardProps {
  asset: string; // "EUR/USD" | "XAU/USD" | etc.
  session: "london" | "ny" | "asia";
  timestamp: string; // ISO
  conviction: { bias: Bias; value: number };
  magnitude: { low: number; high: number; unit: "pips" | "bps" };
  thesis: string; // 3 lignes max (CSS line-clamp-3)
  triggers: Trigger[];
  invalidation: { level: number; condition: string };
  crossAsset: CrossAssetItem[];
  ideas: { top: string; supporting: string[]; risks: string[] };
  confluence: { score: number; drivers: Driver[] };
  calibration: { brier: number; sampleSize: number; trend: Bias };
  /** @deprecated ADR-017 / §7.8 — no order surface. Kept optional so existing
   *  call sites still type-check; the trade plan is no longer rendered. */
  trade?: TradeSetup;
  state?: "default" | "loading" | "expanded" | "error" | "empty";
  onExpand?: () => void;
  className?: string;
}

const SESSION_LABEL: Record<SessionCardProps["session"], string> = {
  london: "Pré-Londres",
  ny: "Pré-NY",
  asia: "Asie",
};

export function SessionCard({
  asset,
  session,
  timestamp,
  conviction,
  magnitude,
  thesis,
  triggers,
  invalidation,
  crossAsset,
  ideas,
  confluence,
  calibration,
  state = "default",
  className,
}: SessionCardProps) {
  if (state === "loading") {
    // Conditional spread — `exactOptionalPropertyTypes` rejects passing
    // `undefined` to an optional `string` prop.
    return <SessionCardSkeleton {...(className ? { className } : {})} />;
  }

  return (
    <article
      data-state={state}
      className={cn(
        "rounded-xl border border-[var(--color-border-default)] bg-[var(--color-bg-surface)] p-6 shadow-[var(--shadow-md)]",
        "flex flex-col gap-5",
        className,
      )}
      aria-labelledby={`sc-${asset}-title`}
    >
      {/* Bloc 1 — Header + conviction */}
      <header className="flex items-start justify-between gap-4">
        <div>
          <h3
            id={`sc-${asset}-title`}
            className="flex items-baseline gap-2 text-lg font-semibold text-[var(--color-text-primary)]"
          >
            <span className="font-mono">{asset}</span>
            <span className="font-mono text-xs uppercase tracking-widest text-[var(--color-text-muted)]">
              {SESSION_LABEL[session]}
            </span>
          </h3>
          <time
            dateTime={timestamp}
            className="font-mono text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]"
          >
            {new Date(timestamp).toLocaleString("fr-FR", {
              dateStyle: "short",
              timeStyle: "short",
            })}
          </time>
        </div>
        <BiasIndicator
          bias={conviction.bias}
          value={conviction.value}
          unit="%"
          variant="large"
          size="xl"
          withGlow
          magnitude={{ low: magnitude.low, high: magnitude.high }}
          magnitudeUnit={magnitude.unit}
        />
      </header>

      {/* Bloc 2 — Thesis */}
      <p className="text-sm leading-relaxed text-[var(--color-text-secondary)]">{thesis}</p>

      {/* Bloc 3 — Triggers / catalysts */}
      {triggers.length > 0 && (
        <div>
          <h4 className="mb-2 font-mono text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]">
            Catalyseurs
          </h4>
          <ul className="flex flex-wrap gap-2">
            {triggers.map((t) => (
              <li
                key={t.id}
                className="flex items-center gap-1.5 rounded border border-[var(--color-border-subtle)] bg-[var(--color-bg-elevated)] px-2 py-1 font-mono text-xs text-[var(--color-text-secondary)]"
              >
                {t.importance === "high" && (
                  <span
                    aria-hidden="true"
                    className="h-1.5 w-1.5 rounded-full bg-[var(--color-warn)]"
                  />
                )}
                <span>{t.label}</span>
                <time dateTime={t.scheduledAt} className="text-[var(--color-text-muted)]">
                  {new Date(t.scheduledAt).toLocaleTimeString("fr-FR", {
                    hour: "2-digit",
                    minute: "2-digit",
                  })}
                </time>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Bloc 4 — Invalidation */}
      <dl className="rounded border border-[var(--color-bear)]/30 bg-[var(--color-bear)]/5 px-3 py-2">
        <dt className="font-mono text-[10px] uppercase tracking-widest text-[var(--color-bear)]">
          Invalidation
        </dt>
        <dd className="mt-0.5 flex items-baseline gap-2 text-sm">
          <span className="font-mono text-[var(--color-text-primary)] tabular-nums">
            {invalidation.level}
          </span>
          <span className="text-[var(--color-text-secondary)]">{invalidation.condition}</span>
        </dd>
      </dl>

      {/* Bloc 5 — Cross-asset map */}
      {crossAsset.length > 0 && (
        <div>
          <h4 className="mb-2 font-mono text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]">
            Inter-actifs
          </h4>
          <ul className="grid grid-cols-2 gap-x-4 gap-y-1.5 sm:grid-cols-3">
            {crossAsset.map((ca) => (
              <li key={ca.symbol} className="flex items-center justify-between gap-2 text-xs">
                <span className="font-mono text-[var(--color-text-muted)]">{ca.symbol}</span>
                <BiasIndicator bias={ca.bias} value={ca.value} variant="compact" size="xs" />
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Bloc 6 — Idea split */}
      <div className="grid grid-cols-3 gap-3 border-t border-[var(--color-border-subtle)] pt-4">
        <IdeaCol label="Idée principale" items={[ideas.top]} accent="bull" />
        <IdeaCol label="Arguments" items={ideas.supporting} accent="neutral" />
        <IdeaCol label="Risques" items={ideas.risks} accent="bear" />
      </div>

      {/* Bloc 7 — Confluence (collapsible) */}
      <details className="group rounded border border-[var(--color-border-subtle)] bg-[var(--color-bg-elevated)] open:bg-[var(--color-bg-elevated)]">
        <summary className="flex cursor-pointer items-center justify-between gap-3 px-3 py-2 text-sm">
          <span className="font-mono uppercase tracking-widest text-[10px] text-[var(--color-text-muted)]">
            Confluence
          </span>
          <span className="font-mono tabular-nums text-[var(--color-text-primary)]">
            {confluence.score.toFixed(1)}/10
          </span>
        </summary>
        <ul className="space-y-1 border-t border-[var(--color-border-subtle)] px-3 py-2 text-xs">
          {confluence.drivers.map((d) => (
            <li key={d.factor} className="flex items-baseline justify-between gap-2">
              <span className="text-[var(--color-text-secondary)]">{d.factor}</span>
              <BiasIndicator
                bias={d.contribution > 0.05 ? "bull" : d.contribution < -0.05 ? "bear" : "neutral"}
                value={d.contribution * 100}
                unit="pp"
                variant="compact"
                size="xs"
              />
            </li>
          ))}
        </ul>
      </details>

      {/* Bloc 8 — Calibration footer */}
      <footer className="flex items-center justify-between border-t border-[var(--color-border-subtle)] pt-3 font-mono text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]">
        <span>
          Fiabilité{" "}
          <span className="tabular-nums text-[var(--color-text-secondary)]">
            {calibration.brier.toFixed(3)}
          </span>{" "}
          · n=
          <span className="tabular-nums text-[var(--color-text-secondary)]">
            {calibration.sampleSize}
          </span>
        </span>
        <BiasIndicator
          bias={calibration.trend}
          value={0}
          unit="%"
          variant="compact"
          size="xs"
          ariaLabel={`Tendance fiabilité : ${calibration.trend}`}
        />
      </footer>

      {/* ADR-017 / §7.8 — pas de bloc « Trade plan » (entry/SL/TP/trail) : la
          carte n'émet jamais d'ordre. L'invalidation (Bloc 4) couvre, de façon
          descriptive, « ce qui casserait la lecture ». */}
    </article>
  );
}

function IdeaCol({
  label,
  items,
  accent,
}: {
  label: string;
  items: string[];
  accent: "bull" | "bear" | "neutral";
}) {
  const accentColor =
    accent === "bull"
      ? "var(--color-bull)"
      : accent === "bear"
        ? "var(--color-bear)"
        : "var(--color-text-muted)";
  return (
    <div>
      <h4
        className="mb-1.5 font-mono text-[10px] uppercase tracking-widest"
        style={{ color: accentColor }}
      >
        {label}
      </h4>
      <ul className="space-y-1 text-xs text-[var(--color-text-secondary)]">
        {items.map((it, i) => (
          <li key={i}>{it}</li>
        ))}
      </ul>
    </div>
  );
}

function SessionCardSkeleton({ className }: { className?: string }) {
  return (
    <article
      aria-busy="true"
      aria-label="Chargement de la session"
      className={cn(
        "rounded-xl border border-[var(--color-border-default)] bg-[var(--color-bg-surface)] p-6 shadow-[var(--shadow-md)]",
        "flex flex-col gap-5 motion-safe:animate-pulse",
        className,
      )}
    >
      <div className="flex items-start justify-between gap-4">
        <div className="space-y-2">
          <div className="h-5 w-32 rounded bg-[var(--color-bg-elevated)]" />
          <div className="h-3 w-24 rounded bg-[var(--color-bg-elevated)]" />
        </div>
        <div className="h-10 w-20 rounded bg-[var(--color-bg-elevated)]" />
      </div>
      <div className="space-y-2">
        <div className="h-3 w-full rounded bg-[var(--color-bg-elevated)]" />
        <div className="h-3 w-5/6 rounded bg-[var(--color-bg-elevated)]" />
        <div className="h-3 w-2/3 rounded bg-[var(--color-bg-elevated)]" />
      </div>
      <div className="h-12 w-full rounded bg-[var(--color-bg-elevated)]" />
    </article>
  );
}
