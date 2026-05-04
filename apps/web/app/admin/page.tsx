/**
 * /admin — operational status snapshot.
 *
 * Renders the /v1/admin/status payload : table row counts + per-asset
 * card stats (n_total / approved / amendments / blocked + avg duration
 * + avg conviction). Useful for Eliot to verify everything is humming.
 */

import { ApiError } from "../../lib/api";

export const metadata = { title: "Admin · Status" };
export const dynamic = "force-dynamic";
export const revalidate = 30;

interface TableCount {
  table: string;
  rows: number;
  most_recent_at: string | null;
}

interface CardStat {
  asset: string;
  n_total: number;
  n_approved: number;
  n_amendments: number;
  n_blocked: number;
  avg_duration_ms: number;
  avg_conviction_pct: number;
  last_at: string | null;
}

interface StatusOut {
  generated_at: string;
  tables: TableCount[];
  cards: CardStat[];
  n_cards_24h: number;
  n_cards_total: number;
  last_card_at: string | null;
  claude_runner_url: string | null;
}

async function fetchStatus(): Promise<StatusOut> {
  const r = await fetch(
    `${process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000"}/v1/admin/status`,
    { next: { revalidate: 30 }, headers: { Accept: "application/json" } }
  );
  if (!r.ok) throw new ApiError(`status ${r.status}`, r.status);
  return r.json() as Promise<StatusOut>;
}

const fmtTime = (iso: string | null) => {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("fr-FR", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "Europe/Paris",
  });
};

const ageBucket = (iso: string | null): string => {
  if (!iso) return "stale";
  const ageMin = (Date.now() - new Date(iso).getTime()) / 60_000;
  if (ageMin < 30) return "fresh";
  if (ageMin < 60 * 6) return "recent";
  if (ageMin < 60 * 24) return "today";
  return "stale";
};

const AGE_BADGE: Record<string, string> = {
  fresh: "bg-emerald-900/40 text-emerald-200",
  recent: "bg-emerald-950/40 text-emerald-300",
  today: "bg-amber-900/30 text-amber-300",
  stale: "bg-neutral-800 text-neutral-500",
};

export default async function AdminPage() {
  let s: StatusOut | null = null;
  let err: string | null = null;
  try {
    s = await fetchStatus();
  } catch (e) {
    err = e instanceof Error ? e.message : "unknown";
  }

  return (
    <div className="max-w-6xl mx-auto px-4 py-6 space-y-6">
      <header>
        <h1 className="text-2xl font-semibold text-neutral-100">
          Admin · État opérationnel
        </h1>
        <p className="text-sm text-neutral-400 mt-1">
          Compteurs DB live et stats des cartes récentes. Auto-refresh
          toutes les 30s.
        </p>
      </header>

      {err ? (
        <div
          role="alert"
          className="rounded border border-red-700/40 bg-red-900/20 px-3 py-2 text-sm text-red-200"
        >
          {err}
        </div>
      ) : s ? (
        <>
          {/* Top stats */}
          <section className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <Stat label="Cartes 24h" value={s.n_cards_24h} />
            <Stat label="Cartes (total)" value={s.n_cards_total} />
            <Stat
              label="Dernière carte"
              value={fmtTime(s.last_card_at)}
              mono={false}
            />
            <Stat
              label="Claude-runner"
              value={s.claude_runner_url ? "configuré" : "n/a"}
              mono={false}
            />
          </section>

          {/* Tables */}
          <section>
            <h2 className="text-lg font-semibold text-neutral-100 mb-3">
              Tables collectors ({s.tables.length})
            </h2>
            <div className="overflow-x-auto rounded-lg border border-neutral-800">
              <table className="w-full text-sm">
                <thead className="bg-neutral-900/40 text-neutral-400 text-xs">
                  <tr>
                    <th className="px-3 py-2 text-left font-medium">Table</th>
                    <th className="px-3 py-2 text-right font-medium">
                      Lignes
                    </th>
                    <th className="px-3 py-2 text-right font-medium">
                      Dernière entrée
                    </th>
                    <th className="px-3 py-2 text-left font-medium">Âge</th>
                  </tr>
                </thead>
                <tbody>
                  {s.tables.map((t) => {
                    const bucket = ageBucket(t.most_recent_at);
                    return (
                      <tr
                        key={t.table}
                        className="border-t border-neutral-800 text-neutral-200"
                      >
                        <td className="px-3 py-2 font-mono">{t.table}</td>
                        <td className="px-3 py-2 text-right font-mono">
                          {t.rows.toLocaleString()}
                        </td>
                        <td className="px-3 py-2 text-right font-mono text-neutral-400">
                          {fmtTime(t.most_recent_at)}
                        </td>
                        <td className="px-3 py-2">
                          <span
                            className={`inline-flex px-1.5 py-0.5 rounded text-[10px] font-mono ${AGE_BADGE[bucket]}`}
                          >
                            {bucket}
                          </span>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </section>

          {/* Cards per asset */}
          <section>
            <h2 className="text-lg font-semibold text-neutral-100 mb-3">
              Cartes session par actif ({s.cards.length})
            </h2>
            {s.cards.length === 0 ? (
              <p className="text-sm text-neutral-500">
                Pas encore de carte persistée.
              </p>
            ) : (
              <div className="overflow-x-auto rounded-lg border border-neutral-800">
                <table className="w-full text-sm">
                  <thead className="bg-neutral-900/40 text-neutral-400 text-xs">
                    <tr>
                      <th className="px-3 py-2 text-left font-medium">Actif</th>
                      <th className="px-3 py-2 text-right font-medium">Total</th>
                      <th className="px-3 py-2 text-right font-medium">
                        Approved
                      </th>
                      <th className="px-3 py-2 text-right font-medium">
                        Amendments
                      </th>
                      <th className="px-3 py-2 text-right font-medium">
                        Blocked
                      </th>
                      <th className="px-3 py-2 text-right font-medium">
                        Avg dur (s)
                      </th>
                      <th className="px-3 py-2 text-right font-medium">
                        Avg conv
                      </th>
                      <th className="px-3 py-2 text-right font-medium">
                        Dernière
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {s.cards.map((c) => (
                      <tr
                        key={c.asset}
                        className="border-t border-neutral-800 text-neutral-200"
                      >
                        <td className="px-3 py-2 font-mono">
                          {c.asset.replace(/_/g, "/")}
                        </td>
                        <td className="px-3 py-2 text-right font-mono">
                          {c.n_total}
                        </td>
                        <td className="px-3 py-2 text-right font-mono text-emerald-300">
                          {c.n_approved}
                        </td>
                        <td className="px-3 py-2 text-right font-mono text-amber-300">
                          {c.n_amendments}
                        </td>
                        <td className="px-3 py-2 text-right font-mono text-rose-300">
                          {c.n_blocked}
                        </td>
                        <td className="px-3 py-2 text-right font-mono">
                          {(c.avg_duration_ms / 1000).toFixed(1)}
                        </td>
                        <td className="px-3 py-2 text-right font-mono">
                          {c.avg_conviction_pct.toFixed(1)}%
                        </td>
                        <td className="px-3 py-2 text-right text-[11px] text-neutral-400">
                          {fmtTime(c.last_at)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          <p className="text-[11px] text-neutral-500 italic">
            Snapshot généré {fmtTime(s.generated_at)}.
          </p>
        </>
      ) : null}
    </div>
  );
}

function Stat({
  label,
  value,
  mono = true,
}: {
  label: string;
  value: number | string;
  mono?: boolean;
}) {
  return (
    <div className="rounded-lg border border-neutral-800 bg-neutral-900/30 p-3">
      <p className="text-[11px] text-neutral-500">{label}</p>
      <p
        className={[
          "mt-1 text-lg font-semibold text-neutral-100",
          mono ? "font-mono" : "",
        ].join(" ")}
      >
        {value}
      </p>
    </div>
  );
}
