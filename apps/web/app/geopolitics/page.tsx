/**
 * /geopolitics — GDELT-driven heatmap of recent global events.
 *
 * VISION_2026 delta Q.
 */

import { ApiError } from "../../lib/api";
import { GeopoliticsGlobe } from "../../components/geopolitics-globe";

export const metadata = { title: "Géopolitique" };
export const dynamic = "force-dynamic";
export const revalidate = 300;

interface CountryHotspot {
  country: string;
  count: number;
  mean_tone: number;
  most_negative_title: string | null;
}

interface HeatmapOut {
  window_hours: number;
  n_events: number;
  countries: CountryHotspot[];
}

async function fetchHeatmap(hours: number): Promise<HeatmapOut> {
  const r = await fetch(
    `${process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000"}/v1/geopolitics/heatmap?hours=${hours}`,
    { next: { revalidate: 300 }, headers: { Accept: "application/json" } },
  );
  if (!r.ok) throw new ApiError(`/v1/geopolitics/heatmap ${r.status}`, r.status);
  return r.json() as Promise<HeatmapOut>;
}

export default async function GeopoliticsPage() {
  let report24: HeatmapOut | null = null;
  let report168: HeatmapOut | null = null;
  let error: string | null = null;
  try {
    [report24, report168] = await Promise.all([fetchHeatmap(24), fetchHeatmap(168)]);
  } catch (e) {
    error = e instanceof Error ? e.message : "unknown";
  }

  const showing = report24 ?? report168;

  return (
    <div className="max-w-6xl mx-auto px-4 py-6 space-y-6">
      <header>
        <h1 className="text-2xl font-semibold text-neutral-100">Géopolitique</h1>
        <p className="text-sm text-neutral-400 mt-1 max-w-2xl">
          Carte du flux GDELT 2.0 sur les dernières 24h. Chaque pays est un point, sa taille =
          nombre d&apos;événements, sa couleur = tonalité moyenne (rouge négatif → vert positif). Le
          graphe est une version compressée — les coordonnées sont projetées en équirectangulaire
          simple, pas un vrai globe 3D.
        </p>
      </header>

      {error ? (
        <div
          role="alert"
          className="rounded border border-red-700/40 bg-red-900/20 px-3 py-2 text-sm text-red-200"
        >
          {error}
        </div>
      ) : (
        <>
          <section>
            <header className="mb-3 flex items-baseline justify-between">
              <h2 className="text-lg font-semibold text-neutral-100">Heatmap 24h</h2>
              <p className="text-[11px] text-neutral-500">
                {showing?.n_events ?? 0} événements · {showing?.countries.length ?? 0} pays
                distincts
              </p>
            </header>
            {showing && showing.countries.length > 0 ? (
              <GeopoliticsGlobe countries={showing.countries} />
            ) : (
              <p className="text-sm text-neutral-500">
                Pas encore d&apos;événements GDELT dans la fenêtre. Le collector tourne toutes les
                2h — patiente le prochain tick.
              </p>
            )}
          </section>

          {/* Top countries table */}
          {showing && showing.countries.length > 0 && (
            <section>
              <h2 className="text-lg font-semibold text-neutral-100 mb-3">
                Top pays par volume d&apos;événements
              </h2>
              <div className="overflow-x-auto rounded-lg border border-neutral-800">
                <table className="w-full text-sm">
                  <thead className="bg-neutral-900/40 text-neutral-400 text-xs">
                    <tr>
                      <th className="px-3 py-2 text-left font-medium">Pays</th>
                      <th className="px-3 py-2 text-right font-medium">Événements</th>
                      <th className="px-3 py-2 text-right font-medium">Tone moyen</th>
                      <th className="px-3 py-2 text-left font-medium">Titre le plus négatif</th>
                    </tr>
                  </thead>
                  <tbody>
                    {showing.countries.slice(0, 20).map((c) => (
                      <tr key={c.country} className="border-t border-neutral-800 text-neutral-200">
                        <td className="px-3 py-2 font-mono">{c.country}</td>
                        <td className="px-3 py-2 text-right font-mono">{c.count}</td>
                        <td
                          className={[
                            "px-3 py-2 text-right font-mono",
                            c.mean_tone < -1
                              ? "text-rose-300"
                              : c.mean_tone > 1
                                ? "text-emerald-300"
                                : "text-neutral-300",
                          ].join(" ")}
                        >
                          {c.mean_tone >= 0 ? "+" : ""}
                          {c.mean_tone.toFixed(2)}
                        </td>
                        <td className="px-3 py-2 text-neutral-400 italic line-clamp-1">
                          {c.most_negative_title ?? "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          )}
        </>
      )}
    </div>
  );
}
