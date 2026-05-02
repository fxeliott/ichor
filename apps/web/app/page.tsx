export default function HomePage() {
  return (
    <main className="min-h-screen flex flex-col items-center justify-center p-8 gap-6">
      <h1 className="text-4xl font-semibold tracking-tight">Ichor</h1>
      <p className="text-neutral-400 max-w-md text-center">
        Phase 0 — infrastructure setup. The dashboard will populate as the 32
        Phase 0 criteria turn green.
      </p>
      <div
        role="note"
        className="mt-8 max-w-xl border border-amber-700/40 bg-amber-950/20 text-amber-200/90 rounded-md p-4 text-sm leading-relaxed"
      >
        <strong className="block mb-1">Avis IA — EU AI Act Article 50</strong>
        Contenu généré par intelligence artificielle. Ichor produit des
        analyses non personnalisées à but informatif uniquement. Ce contenu ne
        constitue pas un conseil en investissement personnalisé au sens de la
        position AMF DOC-2008-23.
      </div>
    </main>
  );
}
