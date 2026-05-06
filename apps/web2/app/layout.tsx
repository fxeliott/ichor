import type { Metadata, Viewport } from "next";
import { Geist, JetBrains_Mono, Fraunces } from "next/font/google";

import { AIDisclosureBanner } from "@/components/ui/ai-disclosure-banner";
import { LegalFooter } from "@/components/ui/legal-footer";

import "./globals.css";

// Self-hosted via next/font/google — no requests sent to fonts.google.com
// from the browser. CSS variables are bound into Tailwind v4 utilities via
// `@theme inline` in app/globals.css.
//
// Decisions (cf SPEC.md §14):
//   - Geist Sans for UI density
//   - JetBrains Mono for data + tickers (tabular-nums via font-feature-settings)
//   - Fraunces for editorial surfaces (briefings, /learn) — variable axes
//     opsz/SOFT/WONK enabled for optical-size adjustments at large sizes.

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
  display: "swap",
});

const jetbrainsMono = JetBrains_Mono({
  variable: "--font-jetbrains-mono",
  subsets: ["latin"],
  display: "swap",
});

const fraunces = Fraunces({
  variable: "--font-fraunces",
  subsets: ["latin"],
  display: "swap",
  axes: ["opsz", "SOFT", "WONK"],
});

export const metadata: Metadata = {
  title: { default: "Ichor", template: "%s · Ichor" },
  description:
    "Living macro entity — pré-trade context premium. Macro, sentiment, géopolitique, options & sessions sur 8 actifs.",
  applicationName: "Ichor",
  robots: { index: false, follow: false },
  manifest: "/manifest.webmanifest",
};

// Single source of truth for theme color — matches manifest.webmanifest and
// --color-bg-base in globals.css. See SPEC.md §2.2 #3 (theme color triple
// reconciliation).
export const viewport: Viewport = {
  themeColor: "#04070C",
  colorScheme: "dark",
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html
      lang="fr"
      className={`${geistSans.variable} ${jetbrainsMono.variable} ${fraunces.variable}`}
    >
      <body className="min-h-screen antialiased">
        {/* WCAG 2.4.1 — skip link */}
        <a
          href="#main"
          className="sr-only focus:not-sr-only focus:fixed focus:left-2 focus:top-2 focus:z-50 focus:rounded focus:bg-[var(--color-bull)] focus:px-3 focus:py-1.5 focus:text-black"
        >
          Aller au contenu principal
        </a>
        {/* EU AI Act Article 50 §1 + §5 — permanent AI disclosure (not dismissible). */}
        <AIDisclosureBanner />
        <main id="main" className="relative">
          {children}
        </main>
        {/* AMF DOC-2008-23 + MiFID 2 + EU AI Act §50 §4 boundary statement. */}
        <LegalFooter />
      </body>
    </html>
  );
}
