// Shared hourly-volatility report: the median heatmap (best/worst hour
// highlighted), the p75 intraday-volatility envelope, and the
// London/NY-vs-Asia session averages. Extracted from the standalone
// `/hourly-volatility/[asset]` page (r120, doctrine #9 anti-accumulation)
// so the PRIMARY `/briefing/[asset]` page consumes the SAME component —
// one brain, two views (the r71/r105 extract-to-shared pattern). Pure
// presentational, RSC-safe (NO "use client" — consumed by two server
// pages, the lesson-#5 RSC-leak discipline). The 3 sub-components are
// the VERBATIM pre-r120 page-local bodies (byte-identical logic, the
// r71/r105 zero-behaviour-change regression discipline) — the ONLY
// post-extraction delta is the `headingLevel` threading applied for the
// concordant r120 3-reviewer fix (see the prop comment below): with the
// default 2 the standalone page renders byte-identical <h2>s.

import { BarSeries } from "@/components/microchart/BarSeries";
import { isLive, type HourlyVolOut } from "@/lib/api";

export function HourlyVolReport({
  report,
  headingLevel = 2,
}: {
  report: HourlyVolOut | null;
  // r120 review (CONCORDANT ichor-trader R28 YELLOW-3 + ui-designer
  // Important-1 + accessibility-reviewer SHOULD-FIX): the standalone
  // `/hourly-volatility/[asset]` page renders these sub-cards directly
  // under its own page <h1> → default 2 keeps that page's rendered DOM
  // byte-identical (the r71/r105 discipline). The `/briefing/[asset]`
  // host nests them under a section <h2 id="hourly-vol-heading"> and
  // passes 3 so the sub-cards are <h3> — no h2-under-h2 outline flatten.
  headingLevel?: 2 | 3;
}) {
  if (!isLive(report)) {
    return (
      <p className="text-sm text-[var(--color-text-muted)]">
        API indisponible — données intraday non récupérables.
      </p>
    );
  }
  return (
    <>
      <HeatmapBars report={report} level={headingLevel} />
      <Percentile75Bars report={report} level={headingLevel} />
      <SessionAverages report={report} level={headingLevel} />
    </>
  );
}

function HeatmapBars({ report, level }: { report: HourlyVolOut; level: 2 | 3 }) {
  const H = `h${level}` as "h2" | "h3";
  const populated = report.entries.filter((e) => e.n_samples > 0);
  if (populated.length === 0) {
    return (
      <p className="text-sm text-[var(--color-text-muted)]">
        Historique polygon insuffisant pour calculer.
      </p>
    );
  }
  const maxMed = Math.max(...populated.map((e) => e.median_bp));
  const values = report.entries.map((e) => e.median_bp);
  const tones = report.entries.map((e) =>
    e.hour_utc === report.best_hour_utc
      ? "var(--color-bull)"
      : e.hour_utc === report.worst_hour_utc
        ? "var(--color-bear)"
        : "var(--color-accent-cobalt)",
  );
  const titles = report.entries.map(
    (e) =>
      `UTC ${e.hour_utc.toString().padStart(2, "0")}:00 — median ${e.median_bp.toFixed(1)} bp · p75 ${e.p75_bp.toFixed(1)} bp · n=${e.n_samples}`,
  );
  // a11y SHOULD-#1 (r106-class colour-rigor) : a NEUTRAL shape outline
  // on the best/worst extremes — a non-hue cue so the two actionable
  // bars stay distinct from the 22 normal ones under colour-vision
  // deficiency (best-vs-worst itself is also carried by the text
  // legend + aria-label + per-bar <title>). Sparse : undefined → no
  // stroke on the normal bars.
  const strokes = report.entries.map((e) =>
    e.hour_utc === report.best_hour_utc || e.hour_utc === report.worst_hour_utc
      ? "var(--color-text-primary)"
      : undefined,
  );

  return (
    <section
      aria-labelledby="heatmap-heading"
      className="mb-6 rounded-xl border border-[var(--color-border-default)] bg-[var(--color-bg-surface)] p-6 shadow-[var(--shadow-sm)]"
    >
      <H
        id="heatmap-heading"
        className="mb-4 font-mono text-xs uppercase tracking-widest text-[var(--color-text-muted)]"
      >
        Heatmap 24h · UTC
      </H>
      <BarSeries
        values={values}
        max={maxMed}
        tones={tones}
        titles={titles}
        strokes={strokes}
        ariaLabel={`Volatilité médiane par heure UTC — ${report.entries.length} heures, pic ${
          report.best_hour_utc?.toString().padStart(2, "0") ?? "n/a"
        }:00, creux ${report.worst_hour_utc?.toString().padStart(2, "0") ?? "n/a"}:00`}
        width={480}
        height={128}
        className="block w-full"
      />
      <div
        className="mt-1 grid"
        style={{ gridTemplateColumns: "repeat(24, minmax(0, 1fr))" }}
        aria-hidden
      >
        {report.entries.map((e) => (
          <span
            key={e.hour_utc}
            className="text-center font-mono text-[9px] leading-none tabular-nums text-[var(--color-text-muted)]"
          >
            {e.hour_utc.toString().padStart(2, "0")}
          </span>
        ))}
      </div>
      <div className="mt-2 flex flex-wrap gap-x-6 gap-y-1 text-xs text-[var(--color-text-muted)]">
        {report.best_hour_utc !== null && report.entries[report.best_hour_utc] ? (
          <p>
            <span style={{ color: "var(--color-bull)" }}>●</span> Best ·{" "}
            <span className="font-mono">
              {report.best_hour_utc.toString().padStart(2, "0")}:00 UTC
            </span>{" "}
            ({report.entries[report.best_hour_utc]!.median_bp.toFixed(1)} bp median)
          </p>
        ) : null}
        {report.worst_hour_utc !== null && report.entries[report.worst_hour_utc] ? (
          <p>
            <span style={{ color: "var(--color-bear)" }}>●</span> Worst ·{" "}
            <span className="font-mono">
              {report.worst_hour_utc.toString().padStart(2, "0")}:00 UTC
            </span>{" "}
            ({report.entries[report.worst_hour_utc]!.median_bp.toFixed(1)} bp median)
          </p>
        ) : null}
      </div>
    </section>
  );
}

function Percentile75Bars({ report, level }: { report: HourlyVolOut; level: 2 | 3 }) {
  const H = `h${level}` as "h2" | "h3";
  const populated = report.entries.filter((e) => e.n_samples > 0);
  // FAIL-SAFE : when there is no data the `HeatmapBars` section above
  // already carries the user-facing "insufficient" message — the p75
  // envelope just renders nothing (no double message).
  if (populated.length === 0) return null;
  const maxP75 = Math.max(...populated.map((e) => e.p75_bp));
  const valuesP75 = report.entries.map((e) => e.p75_bp);
  const titlesP75 = report.entries.map(
    (e) =>
      `UTC ${e.hour_utc.toString().padStart(2, "0")}:00 — p75 ${e.p75_bp.toFixed(1)} bp · median ${e.median_bp.toFixed(1)} bp · n=${e.n_samples}`,
  );

  return (
    <section
      aria-labelledby="p75-heading"
      className="mb-6 rounded-xl border border-[var(--color-border-default)] bg-[var(--color-bg-surface)] p-6 shadow-[var(--shadow-sm)]"
    >
      <H
        id="p75-heading"
        className="mb-3 font-mono text-xs uppercase tracking-widest text-[var(--color-text-muted)]"
      >
        Enveloppe p75 · 24h UTC
      </H>
      <p className="mb-4 text-sm text-[var(--color-text-secondary)]">
        75ᵉ centile du |log-rendement| par heure — le haut de fourchette intra-horaire, vs le rythme
        typique de la heatmap médiane ci-dessus.
      </p>
      <BarSeries
        values={valuesP75}
        max={maxP75}
        titles={titlesP75}
        ariaLabel={`Volatilité 75e centile (enveloppe) par heure UTC — ${report.entries.length} heures`}
        width={480}
        height={128}
        className="block w-full"
      />
      <div
        className="mt-1 grid"
        style={{ gridTemplateColumns: "repeat(24, minmax(0, 1fr))" }}
        aria-hidden
      >
        {report.entries.map((e) => (
          <span
            key={e.hour_utc}
            className="text-center font-mono text-[9px] leading-none tabular-nums text-[var(--color-text-muted)]"
          >
            {e.hour_utc.toString().padStart(2, "0")}
          </span>
        ))}
      </div>
    </section>
  );
}

function SessionAverages({ report, level }: { report: HourlyVolOut; level: 2 | 3 }) {
  const H = `h${level}` as "h2" | "h3";
  const stats: Array<[string, number | null, "bull" | "neutral"]> = [
    ["London / NY · 07-15 UTC", report.london_session_avg_bp, "bull"],
    ["Asia · 00-06 UTC", report.asian_session_avg_bp, "neutral"],
  ];
  return (
    <section
      aria-labelledby="session-avg-heading"
      className="rounded-xl border border-[var(--color-border-default)] bg-[var(--color-bg-surface)] p-6 shadow-[var(--shadow-sm)]"
    >
      <H
        id="session-avg-heading"
        className="mb-3 font-mono text-xs uppercase tracking-widest text-[var(--color-text-muted)]"
      >
        Moyennes par session
      </H>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {stats.map(([label, val, tone]) => (
          <div
            key={label}
            className="rounded-lg border border-[var(--color-border-subtle)] bg-[var(--color-bg-elevated)] p-4"
          >
            <p className="text-xs uppercase tracking-wide text-[var(--color-text-muted)]">
              {label}
            </p>
            <p
              className="mt-1 font-mono text-2xl tabular-nums"
              style={{
                color: tone === "bull" ? "var(--color-bull)" : "var(--color-text-secondary)",
              }}
            >
              {val !== null ? `${val.toFixed(1)} bp` : "n/a"}
            </p>
          </div>
        ))}
      </div>
      <p className="mt-3 text-[11px] text-[var(--color-text-muted)]">
        1 bp = 0.01 % de variation moyenne par bar 1-min. Des moyennes élevées sur la session
        Londres/NY confirment la fenêtre de trading.
      </p>
    </section>
  );
}
