import Link from "next/link";
import { EmptyState } from "@ichor/ui";
import {
  ApiError,
  listModels,
  listPredictions,
  type ModelSummary,
  type PredictionRow,
} from "../../lib/api";

export const metadata = {
  title: "Portfolio (paper)",
};

export const dynamic = "force-dynamic";
export const revalidate = 60;

const fmtAt = (iso: string) =>
  new Date(iso).toLocaleString("fr-FR", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "Europe/Paris",
  });


function PaperBanner() {
  return (
    <aside
      role="note"
      className="rounded-md border border-emerald-700/50 bg-emerald-950/30 px-3 py-2 text-sm text-emerald-100 mb-6"
    >
      <strong className="font-semibold">Mode PAPER uniquement.</strong>
      &nbsp;Aucune position réelle, aucun capital engagé. Ce dashboard
      audite les prédictions historiques persistées dans{" "}
      <code className="px-1 rounded bg-emerald-900/40 font-mono text-xs">
        predictions_audit
      </code>
      . Conformément à <Link href="https://github.com/fxeliott/ichor/blob/main/docs/decisions/ADR-016-paper-only-default.md"
        className="underline-offset-2 hover:underline">ADR-016</Link>, aucun
      passage en live trading sans escalade explicite.
    </aside>
  );
}


export default async function PortfolioPage() {
  let models: ModelSummary[] = [];
  let recent: PredictionRow[] = [];
  let error: string | null = null;

  try {
    [models, recent] = await Promise.all([
      listModels(),
      listPredictions({ sinceDays: 30, limit: 20 }),
    ]);
  } catch (err) {
    error =
      err instanceof ApiError
        ? err.message
        : err instanceof Error
          ? err.message
          : "unknown error";
  }

  const totalPredictions = models.reduce((s, m) => s + m.n_predictions, 0);

  return (
    <main className="max-w-4xl mx-auto px-4 py-6">
      <header className="mb-6">
        <h1 className="text-2xl font-semibold text-neutral-100 mb-1">
          Portfolio
        </h1>
        <p className="text-sm text-neutral-400">
          Audit des prédictions ML — uniquement paper. Le mode live trading
          est interdit par contrat ADR-016.
        </p>
      </header>

      <PaperBanner />

      {error ? (
        <EmptyState
          title="API injoignable"
          description={`Détails techniques : ${error}`}
        />
      ) : (
        <>
          <section
            aria-labelledby="models-section"
            className="mb-8"
          >
            <h2
              id="models-section"
              className="text-sm font-medium text-neutral-200 mb-3"
            >
              Modèles déployés
            </h2>
            {models.length === 0 ? (
              <EmptyState
                title="Aucun modèle entraîné"
                description="La table predictions_audit est vide. Lance scripts/hetzner/run_first_model_e2e.py pour entraîner un premier modèle bout-en-bout."
              />
            ) : (
              <div className="grid gap-2">
                {models.map((m) => (
                  <article
                    key={m.model_id}
                    className="rounded border border-neutral-800 bg-neutral-900/40 px-4 py-3"
                  >
                    <div className="flex items-baseline justify-between gap-3 mb-2">
                      <code className="text-sm font-mono text-neutral-100">
                        {m.model_id}
                      </code>
                      <span className="text-[11px] text-neutral-500 font-mono">
                        {m.n_predictions.toLocaleString("fr-FR")} prédictions
                      </span>
                    </div>
                    <div className="flex items-baseline gap-3 text-xs text-neutral-400">
                      <span>
                        actif :{" "}
                        {m.asset ? (
                          <Link
                            href={`/assets/${m.asset}`}
                            className="font-mono text-neutral-200 hover:text-emerald-300"
                          >
                            {m.asset.replace("_", "/")}
                          </Link>
                        ) : (
                          <span className="text-neutral-500">multi</span>
                        )}
                      </span>
                      <span>·</span>
                      <span>
                        Brier moyen :{" "}
                        <span className="font-mono text-neutral-200">
                          {m.avg_brier !== null ? m.avg_brier.toFixed(3) : "n/a"}
                        </span>
                      </span>
                      {m.earliest && m.latest && (
                        <>
                          <span>·</span>
                          <span className="font-mono text-neutral-500">
                            {new Date(m.earliest).toISOString().slice(0, 10)} →{" "}
                            {new Date(m.latest).toISOString().slice(0, 10)}
                          </span>
                        </>
                      )}
                    </div>
                  </article>
                ))}
              </div>
            )}

            <p className="mt-3 text-[11px] text-neutral-500">
              Total : {totalPredictions.toLocaleString("fr-FR")} prédictions
              auditées dans la table TimescaleDB{" "}
              <code className="font-mono">predictions_audit</code>.
            </p>
          </section>

          <section
            aria-labelledby="recent-section"
            className="mb-8"
          >
            <h2
              id="recent-section"
              className="text-sm font-medium text-neutral-200 mb-3"
            >
              20 prédictions les plus récentes (30 derniers jours)
            </h2>
            {recent.length === 0 ? (
              <EmptyState
                title="Aucune prédiction récente"
                description="Soit aucun modèle ne tourne en cron pour l'instant, soit les fenêtres sont expirées. Vérifier les timers ichor-collector / ichor-briefing."
              />
            ) : (
              <div className="overflow-x-auto rounded border border-neutral-800">
                <table className="w-full text-sm">
                  <thead className="bg-neutral-900/60 text-xs text-neutral-400">
                    <tr>
                      <th className="text-left px-3 py-2">Date</th>
                      <th className="text-left px-3 py-2">Asset</th>
                      <th className="text-left px-3 py-2">Direction</th>
                      <th className="text-right px-3 py-2">P</th>
                      <th className="text-left px-3 py-2 hidden md:table-cell">Modèle</th>
                    </tr>
                  </thead>
                  <tbody className="text-neutral-200">
                    {recent.map((p) => (
                      <tr
                        key={p.id}
                        className="border-t border-neutral-800 hover:bg-neutral-900/40"
                      >
                        <td className="px-3 py-2 font-mono text-[11px] text-neutral-400">
                          {fmtAt(p.generated_at)}
                        </td>
                        <td className="px-3 py-2">
                          <Link
                            href={`/assets/${p.asset}`}
                            className="font-mono hover:text-emerald-300"
                          >
                            {p.asset.replace("_", "/")}
                          </Link>
                        </td>
                        <td className={
                          "px-3 py-2 font-mono " +
                          (p.direction === "long"
                            ? "text-emerald-300"
                            : p.direction === "short"
                              ? "text-red-300"
                              : "text-neutral-400")
                        }>
                          {p.direction}
                        </td>
                        <td className="px-3 py-2 text-right font-mono">
                          {(p.calibrated_probability ?? p.raw_score).toFixed(3)}
                        </td>
                        <td className="px-3 py-2 hidden md:table-cell font-mono text-[11px] text-neutral-500">
                          {p.model_id}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          <section
            aria-labelledby="kill-section"
            className="rounded-md border border-amber-700/40 bg-amber-950/20 p-4"
          >
            <h2
              id="kill-section"
              className="text-sm font-medium text-amber-100 mb-2"
            >
              Kill switch
            </h2>
            <p className="text-xs text-amber-200/90 leading-relaxed">
              Pour halter immédiatement toute génération d&apos;ordres
              (utile en cas de comportement anormal d&apos;un modèle),
              `touch /etc/ichor/KILL_SWITCH` sur Hetzner. Voir{" "}
              <Link
                href="https://github.com/fxeliott/ichor/blob/main/docs/runbooks/RUNBOOK-012-kill-switch-trip.md"
                className="underline hover:no-underline"
              >
                RUNBOOK-012
              </Link>
              .
            </p>
          </section>
        </>
      )}
    </main>
  );
}
