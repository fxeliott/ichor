import type { Metadata, Viewport } from "next";
import { Geist, JetBrains_Mono, Fraunces, Space_Grotesk } from "next/font/google";

import { AuroraBackground } from "@/components/ambient/aurora-background";
import { RegimeAmbientProvider } from "@/components/ambient/regime-ambient-provider";
import { CommandPalette } from "@/components/cmdk/command-palette";
import { MotionProvider } from "@/components/motion/motion-provider";
import { TopNav } from "@/components/nav/top-nav";
import { LegalFooter } from "@/components/ui/legal-footer";
import { Toaster } from "@/components/ui/toaster";

import "./globals.css";

// Self-hosted via next/font/google — no requests sent to fonts.google.com
// from the browser. CSS variables are bound into Tailwind v4 utilities via
// `@theme inline` in app/globals.css.
//
// Decisions (cf SPEC.md §14 + refonte 2026 §typo hybride) :
//   - Space Grotesk for the tech/display voice (cockpit titles, big numbers
//     framing) — bound to `--font-display`.
//   - Geist Sans for UI density (body, controls).
//   - JetBrains Mono for data + tickers (tabular-nums via font-feature-settings).
//   - Fraunces for the editorial/narrative voice (coach prose, /learn) — kept
//     as `font-serif` so the storytelling surfaces stay warm.

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
  display: "swap",
});

const spaceGrotesk = Space_Grotesk({
  variable: "--font-space-grotesk",
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
  // `display: 'optional'` — Fraunces is editorial-only (coach prose, /learn).
  // If the WOFF2 isn't cached within 100ms, the browser falls back without
  // ever swapping in. Trade-off : first-time visitors see the fallback on
  // editorial copy until cached on a subsequent navigation. Net : zero
  // FOIT/FOUT, tighter LCP on dashboard routes that don't use Fraunces.
  // Source: nextjs.org/docs/app/api-reference/components/font#display
  display: "optional",
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
      className={`${geistSans.variable} ${spaceGrotesk.variable} ${jetbrainsMono.variable} ${fraunces.variable}`}
    >
      <body className="min-h-screen antialiased">
        {/* Aurora-cobalt ambient backdrop — behind all content (z-index:-1). */}
        <AuroraBackground />
        {/* WCAG 2.4.1 — skip link */}
        <a
          href="#main"
          className="sr-only focus:not-sr-only focus:fixed focus:left-2 focus:top-2 focus:z-50 focus:rounded focus:bg-[var(--color-bull)] focus:px-3 focus:py-1.5 focus:text-black"
        >
          Aller au contenu principal
        </a>
        <MotionProvider>
          {/* Phase C QW1 — global macro regime quadrant ambient tint
              (data-regime attribute set on <html> from a zustand store
              persisted in localStorage). */}
          <RegimeAmbientProvider>
            {/* Global navigation. (The top AI banner was removed ; the AI-
                generation disclosure lives in the legal footer per EU AI Act §50.) */}
            <TopNav />
            <main id="main" className="relative">
              {children}
            </main>
            {/* Phase A.9.5 — global Cmd+K palette (Bloomberg-style nav flow). */}
            <CommandPalette />
            {/* Phase A.9.3 — sonner-backed global toast surface. */}
            <Toaster />
            {/* AMF DOC-2008-23 + MiFID 2 + EU AI Act §50 §4 boundary statement. */}
            <LegalFooter />
          </RegimeAmbientProvider>
        </MotionProvider>
      </body>
    </html>
  );
}
