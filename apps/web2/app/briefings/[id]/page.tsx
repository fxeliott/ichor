// /briefings/[id] — single briefing detail (markdown rendered).
//
// Port from apps/web (D.3 sprint). Streams the persisted briefing by id,
// renders the `briefing_markdown` body with remark-gfm. Shows a typed
// header with status, trigger time, assets, and audio link when present.

import { notFound } from "next/navigation";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { apiGet, isLive, type Briefing } from "@/lib/api";

interface PageProps {
  params: Promise<{ id: string }>;
}

export const dynamic = "force-dynamic";
export const revalidate = 30;

export async function generateMetadata({ params }: PageProps) {
  const { id } = await params;
  return { title: `Briefing ${id.slice(0, 8)} · Ichor` };
}

const fmtAt = (iso: string) =>
  new Date(iso).toLocaleString("fr-FR", {
    weekday: "short",
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "Europe/Paris",
  });

export default async function BriefingDetailPage({ params }: PageProps) {
  const { id } = await params;
  const briefing = await apiGet<Briefing>(`/v1/briefings/${id}`, { revalidate: 30 });

  if (!isLive(briefing)) {
    // null = 404 OR API offline. We can't tell apart from this layer ; trigger
    // notFound() in either case so error.tsx isn't shown for a missing id.
    notFound();
  }

  const statusColor =
    briefing.status === "completed"
      ? "var(--color-bull)"
      : briefing.status === "failed"
        ? "var(--color-bear)"
        : "var(--color-text-muted)";

  return (
    <main className="container mx-auto max-w-3xl px-6 py-12">
      <header className="mb-8 border-b border-[var(--color-border-default)] pb-6">
        <p className="font-mono text-xs uppercase tracking-[0.18em] text-[var(--color-text-muted)]">
          Briefing · {briefing.briefing_type}
        </p>
        <div className="mt-3 flex items-baseline justify-between gap-3 flex-wrap">
          <time
            dateTime={briefing.triggered_at}
            className="font-mono text-sm text-[var(--color-text-primary)]"
          >
            {fmtAt(briefing.triggered_at)}
          </time>
          <span
            className="inline-flex items-center gap-1 rounded border px-2 py-0.5 font-mono text-[10px] uppercase tracking-widest"
            style={{ color: statusColor, borderColor: statusColor }}
          >
            {briefing.status}
          </span>
        </div>
        <ul className="mt-3 flex flex-wrap gap-1 font-mono text-[11px]">
          {briefing.assets.map((a) => (
            <li
              key={a}
              className="rounded border border-[var(--color-border-subtle)] bg-[var(--color-bg-elevated)] px-1.5 py-0.5 text-[var(--color-text-muted)]"
            >
              {a}
            </li>
          ))}
        </ul>
        {briefing.claude_duration_ms !== null ? (
          <p className="mt-3 font-mono text-[11px] text-[var(--color-text-muted)]">
            claude duration · {(briefing.claude_duration_ms / 1000).toFixed(1)}s
          </p>
        ) : null}
        {briefing.audio_mp3_url ? (
          <audio controls className="mt-4 w-full" src={briefing.audio_mp3_url}>
            Audio briefing — votre navigateur ne supporte pas l&apos;élément audio.
          </audio>
        ) : null}
      </header>

      <article className="prose-invert text-[var(--color-text-secondary)] leading-relaxed">
        {briefing.briefing_markdown ? (
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            components={{
              h1: ({ children }) => (
                <h1 className="mt-6 mb-3 text-2xl font-semibold text-[var(--color-text-primary)]">
                  {children}
                </h1>
              ),
              h2: ({ children }) => (
                <h2 className="mt-5 mb-2 border-b border-[var(--color-border-subtle)] pb-1 text-lg font-semibold text-[var(--color-text-primary)]">
                  {children}
                </h2>
              ),
              h3: ({ children }) => (
                <h3 className="mt-4 mb-2 text-base font-semibold text-[var(--color-text-primary)]">
                  {children}
                </h3>
              ),
              p: ({ children }) => <p className="my-2">{children}</p>,
              ul: ({ children }) => (
                <ul className="my-2 list-outside list-disc space-y-1 pl-5">{children}</ul>
              ),
              ol: ({ children }) => (
                <ol className="my-2 list-outside list-decimal space-y-1 pl-5">{children}</ol>
              ),
              strong: ({ children }) => (
                <strong className="font-semibold text-[var(--color-text-primary)]">
                  {children}
                </strong>
              ),
              em: ({ children }) => (
                <em className="italic text-[var(--color-text-secondary)]">{children}</em>
              ),
              code: ({ children }) => (
                <code className="rounded bg-[var(--color-bg-elevated)] px-1 py-0.5 font-mono text-[0.9em] text-[var(--color-accent-cobalt)]">
                  {children}
                </code>
              ),
              hr: () => <hr className="my-6 border-[var(--color-border-subtle)]" />,
              a: ({ href, children }) => (
                <a
                  href={href}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-[var(--color-accent-cobalt)] underline-offset-2 hover:underline"
                >
                  {children}
                  <span aria-hidden="true" className="ml-0.5 text-[0.8em]">
                    ↗
                  </span>
                </a>
              ),
              blockquote: ({ children }) => (
                <blockquote className="my-3 border-l-2 border-[var(--color-border-default)] pl-3 italic text-[var(--color-text-muted)]">
                  {children}
                </blockquote>
              ),
              table: ({ children }) => (
                <div className="my-3 overflow-x-auto">
                  <table className="min-w-full border border-[var(--color-border-subtle)] text-sm">
                    {children}
                  </table>
                </div>
              ),
              th: ({ children }) => (
                <th className="border border-[var(--color-border-subtle)] bg-[var(--color-bg-elevated)] px-2 py-1 text-left">
                  {children}
                </th>
              ),
              td: ({ children }) => (
                <td className="border border-[var(--color-border-subtle)] px-2 py-1">{children}</td>
              ),
            }}
          >
            {briefing.briefing_markdown}
          </ReactMarkdown>
        ) : (
          <p className="italic text-[var(--color-text-muted)]">
            Briefing en cours d&apos;assemblage…
          </p>
        )}
      </article>
    </main>
  );
}
