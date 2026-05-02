import { BriefingHeader, DisclaimerBanner } from "@ichor/ui";
import { notFound } from "next/navigation";

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

      <article className="prose prose-invert prose-neutral max-w-none">
        {briefing.briefing_markdown ? (
          // Phase 0: render markdown as preformatted text. Phase 1: real markdown
          // renderer (react-markdown + remark-gfm).
          <pre className="whitespace-pre-wrap font-sans text-base leading-relaxed text-neutral-200">
            {briefing.briefing_markdown}
          </pre>
        ) : (
          <p className="text-neutral-500 italic">Briefing en cours d'assemblage...</p>
        )}
      </article>

      <DisclaimerBanner />
    </main>
  );
}
