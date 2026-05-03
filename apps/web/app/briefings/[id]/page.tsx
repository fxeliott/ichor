import { BriefingHeader, DisclaimerBanner } from "@ichor/ui";
import { notFound } from "next/navigation";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

interface BriefingDetail {
  id: string;
  briefing_type: "pre_londres" | "pre_ny" | "ny_mid" | "ny_close" | "weekly" | "crisis";
  triggered_at: string;
  assets: string[];
  status: "pending" | "context_assembled" | "claude_running" | "completed" | "failed";
  briefing_markdown: string | null;
  claude_duration_ms: number | null;
  audio_mp3_url: string | null;
  created_at: string;
}

async function fetchBriefing(id: string): Promise<BriefingDetail | null> {
  const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";
  const res = await fetch(`${apiUrl}/v1/briefings/${id}`, {
    next: { revalidate: 30 },
  });
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`Failed to fetch briefing ${id}: ${res.status}`);
  return res.json();
}

export default async function BriefingPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const briefing = await fetchBriefing(id);
  if (!briefing) notFound();

  return (
    <main className="max-w-3xl mx-auto px-4 py-8">
      <BriefingHeader
        briefingType={briefing.briefing_type}
        triggeredAt={new Date(briefing.triggered_at)}
        assets={briefing.assets}
        status={briefing.status}
        claudeDurationMs={briefing.claude_duration_ms}
        audioUrl={briefing.audio_mp3_url}
      />

      <article className="text-neutral-200 leading-relaxed">
        {briefing.briefing_markdown ? (
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            components={{
              h1: ({ children }) => (
                <h1 className="text-2xl font-semibold text-neutral-100 mt-6 mb-3">
                  {children}
                </h1>
              ),
              h2: ({ children }) => (
                <h2 className="text-lg font-semibold text-neutral-100 mt-5 mb-2 border-b border-neutral-800 pb-1">
                  {children}
                </h2>
              ),
              h3: ({ children }) => (
                <h3 className="text-base font-semibold text-neutral-100 mt-4 mb-2">
                  {children}
                </h3>
              ),
              p: ({ children }) => <p className="my-2">{children}</p>,
              ul: ({ children }) => (
                <ul className="list-disc list-outside pl-5 my-2 space-y-1">{children}</ul>
              ),
              ol: ({ children }) => (
                <ol className="list-decimal list-outside pl-5 my-2 space-y-1">{children}</ol>
              ),
              strong: ({ children }) => (
                <strong className="text-neutral-50 font-semibold">{children}</strong>
              ),
              em: ({ children }) => (
                <em className="text-neutral-300 italic">{children}</em>
              ),
              code: ({ children }) => (
                <code className="px-1 py-0.5 rounded bg-neutral-800 text-emerald-200 font-mono text-[0.9em]">
                  {children}
                </code>
              ),
              hr: () => <hr className="my-6 border-neutral-800" />,
              a: ({ href, children }) => (
                <a
                  href={href}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-emerald-400 hover:text-emerald-300 underline-offset-2 hover:underline"
                  aria-label={
                    typeof children === "string"
                      ? `${children} (nouvel onglet)`
                      : undefined
                  }
                >
                  {children}
                  <span aria-hidden="true" className="ml-0.5 text-[0.8em]">
                    ↗
                  </span>
                </a>
              ),
              blockquote: ({ children }) => (
                <blockquote className="border-l-2 border-neutral-700 pl-3 text-neutral-400 italic my-3">
                  {children}
                </blockquote>
              ),
              table: ({ children }) => (
                <div className="overflow-x-auto my-3">
                  <table className="min-w-full text-sm border border-neutral-800">
                    {children}
                  </table>
                </div>
              ),
              th: ({ children }) => (
                <th className="border border-neutral-800 bg-neutral-900/60 px-2 py-1 text-left">
                  {children}
                </th>
              ),
              td: ({ children }) => (
                <td className="border border-neutral-800 px-2 py-1">{children}</td>
              ),
            }}
          >
            {briefing.briefing_markdown}
          </ReactMarkdown>
        ) : (
          <p className="text-neutral-500 italic">
            Briefing en cours d'assemblage…
          </p>
        )}
      </article>

      <DisclaimerBanner />
    </main>
  );
}
