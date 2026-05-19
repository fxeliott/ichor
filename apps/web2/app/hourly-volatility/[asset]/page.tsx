// /hourly-volatility/[asset] — 24-bar UTC charts of median + p75
// |log return| bp.
//
// Fetches via the shared `getHourlyVol` wrapper and renders the shared
// <HourlyVolReport> (median heatmap + p75 envelope + session averages).
// r120 extracted that report to `components/hourly-vol/HourlyVolReport`
// (doctrine #9 anti-accumulation) so the primary `/briefing/[asset]`
// page consumes the SAME component — one brain, two views. This page is
// now just the route chrome (breadcrumb + header) around it.

import Link from "next/link";
import { notFound } from "next/navigation";

import { HourlyVolReport } from "@/components/hourly-vol/HourlyVolReport";
import { getHourlyVol } from "@/lib/api";

const SUPPORTED_ASSETS = new Set([
  "EUR_USD",
  "GBP_USD",
  "USD_JPY",
  "AUD_USD",
  "USD_CAD",
  "XAU_USD",
  "NAS100_USD",
  "SPX500_USD",
]);

interface PageProps {
  params: Promise<{ asset: string }>;
}

export const dynamic = "force-dynamic";
export const revalidate = 300;

export async function generateMetadata({ params }: PageProps) {
  const { asset } = await params;
  return { title: `Vol horaire · ${asset.replace(/_/g, "/")} · Ichor` };
}

export default async function HourlyVolPage({ params }: PageProps) {
  const { asset } = await params;
  const slug = asset.toUpperCase();
  if (!SUPPORTED_ASSETS.has(slug)) notFound();

  const report = await getHourlyVol(slug);

  return (
    <main className="container mx-auto max-w-5xl px-6 py-12">
      <nav aria-label="Fil d'Ariane" className="mb-4 text-xs text-[var(--color-text-muted)]">
        <Link href="/" className="hover:text-[var(--color-text-primary)] underline">
          Accueil
        </Link>
        <span className="mx-2">/</span>
        <Link
          href={`/sessions/${slug}`}
          className="hover:text-[var(--color-text-primary)] underline"
        >
          {slug.replace(/_/g, "/")}
        </Link>
        <span className="mx-2">/</span>
        <span className="text-[var(--color-text-primary)]">vol horaire</span>
      </nav>

      <header className="mb-8">
        <p className="font-mono text-xs uppercase tracking-[0.18em] text-[var(--color-text-muted)]">
          Volatilité horaire · 30j
        </p>
        <h1 className="mt-1 text-4xl tracking-tight text-[var(--color-text-primary)]">
          {slug.replace(/_/g, "/")}
        </h1>
        <p className="mt-2 max-w-2xl text-sm text-[var(--color-text-secondary)]">
          Médiane du |log-rendement| par heure UTC sur 30 jours. Quand cet actif bouge vraiment vs
          quand il dort.
        </p>
      </header>

      <HourlyVolReport report={report} />
    </main>
  );
}
