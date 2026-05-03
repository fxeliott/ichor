import Link from "next/link";

export default function NotFound() {
  return (
    <main className="max-w-md mx-auto px-4 py-16 text-center flex flex-col gap-4">
      <h1 className="text-2xl font-semibold text-neutral-100">Introuvable</h1>
      <p className="text-sm text-neutral-400">
        Cette ressource n'existe pas ou n'est plus disponible.
      </p>
      <Link
        href="/"
        className="self-center text-sm text-emerald-400 hover:text-emerald-300 underline-offset-2 hover:underline"
      >
        ← Retour à l'accueil
      </Link>
    </main>
  );
}
