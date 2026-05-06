import type { Metadata, Viewport } from "next";
import Link from "next/link";
import { DisclaimerBanner } from "@ichor/ui";
import { CommandPalette } from "../components/command-palette";
import { EventTicker } from "../components/event-ticker";
import { KeyboardShortcutsModal } from "../components/keyboard-shortcuts";
import { MobileNav } from "../components/mobile-nav";
import { PushToggle } from "../components/push-toggle";
import { StatusDot } from "../components/ui/status-dot";
import { LiveEventsToast } from "./live-events-toast";
import { ServiceWorkerRegister } from "./service-worker-register";
import "./globals.css";

export const metadata: Metadata = {
  title: { default: "Ichor", template: "%s · Ichor" },
  description:
    "Autonomous market intelligence — macro, sentiment, geopol, scénarios SMC sur 8 actifs.",
  applicationName: "Ichor",
  robots: { index: false, follow: false },
  manifest: "/manifest.webmanifest",
};

// Single source of truth for theme color across manifest, viewport meta, and CSS var.
// Matches --color-ichor-deep in app/globals.css (deepest navy in palette).
export const viewport: Viewport = {
  themeColor: "#04070C",
  colorScheme: "dark",
  width: "device-width",
  initialScale: 1,
};

interface NavItem {
  href: string;
  label: string;
  group: "core" | "macro" | "ops";
}

const NAV: NavItem[] = [
  // Core (everyday)
  { href: "/", label: "Aujourd'hui", group: "core" },
  { href: "/sessions", label: "Sessions", group: "core" },
  { href: "/confluence", label: "Confluence", group: "core" },
  // Macro layer
  { href: "/macro-pulse", label: "Macro pulse", group: "macro" },
  { href: "/yield-curve", label: "Curve", group: "macro" },
  { href: "/correlations", label: "Corrélations", group: "macro" },
  { href: "/polymarket-impact", label: "Polymarket", group: "macro" },
  { href: "/narratives", label: "Narratives", group: "macro" },
  { href: "/geopolitics", label: "Geopol", group: "macro" },
  { href: "/knowledge-graph", label: "Graph", group: "macro" },
  // Ops
  { href: "/calibration", label: "Calibration", group: "ops" },
  { href: "/admin", label: "Admin", group: "ops" },
  { href: "/learn", label: "Apprendre", group: "ops" },
];

export default function RootLayout({ children }: { children: React.ReactNode }) {
  const coreNav = NAV.filter((n) => n.group === "core");
  const macroNav = NAV.filter((n) => n.group === "macro");
  const opsNav = NAV.filter((n) => n.group === "ops");

  return (
    <html lang="fr">
      <body className="text-[var(--color-ichor-text)] antialiased min-h-screen flex flex-col">
        {/* WCAG 2.4.1 — Skip link */}
        <a
          href="#main"
          className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-50 focus:px-3 focus:py-1.5 focus:rounded focus:bg-[var(--color-ichor-accent)] focus:text-white"
        >
          Aller au contenu principal
        </a>
        <ServiceWorkerRegister />
        <CommandPalette />
        <KeyboardShortcutsModal />
        <LiveEventsToast />
        <EventTicker />
        <DisclaimerBanner compact />

        <header className="sticky top-0 z-20 border-b border-[var(--color-ichor-border)] bg-[var(--color-ichor-deep)]/80 backdrop-blur-xl">
          <div className="max-w-7xl mx-auto px-4 py-3" aria-label="Navigation principale">
            <nav className="flex items-center gap-5">
              <Link href="/" className="group flex items-center gap-2.5 transition">
                {/* Animated I-mark with cobalt glow */}
                <span className="relative inline-flex items-center justify-center w-8 h-8 rounded-md bg-gradient-to-br from-[var(--color-ichor-accent-deep)] to-[var(--color-ichor-accent)] ichor-glow">
                  <svg
                    width="18"
                    height="18"
                    viewBox="0 0 24 24"
                    aria-hidden="true"
                    className="text-white"
                  >
                    <path
                      d="M3 18 L9 6 L13 14 L17 4 L21 18"
                      stroke="currentColor"
                      strokeWidth="2"
                      fill="none"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                    <circle cx="21" cy="18" r="1.5" fill="currentColor" />
                  </svg>
                </span>
                <div className="flex flex-col leading-tight">
                  <span className="text-base font-semibold tracking-tight bg-gradient-to-br from-white to-[var(--color-ichor-accent-bright)] bg-clip-text text-transparent">
                    Ichor
                  </span>
                  <span className="text-[9px] uppercase tracking-[0.18em] text-[var(--color-ichor-text-faint)] -mt-0.5">
                    Macro intel
                  </span>
                </div>
              </Link>

              {/* Core nav (always visible) */}
              <ul className="hidden lg:flex items-center gap-4 text-sm">
                {coreNav.map((item) => (
                  <li key={item.href}>
                    <Link href={item.href} className="ichor-nav-link">
                      {item.label}
                    </Link>
                  </li>
                ))}
                <li aria-hidden="true" className="w-px h-4 bg-[var(--color-ichor-border)]" />
                {macroNav.map((item) => (
                  <li key={item.href}>
                    <Link href={item.href} className="ichor-nav-link text-xs">
                      {item.label}
                    </Link>
                  </li>
                ))}
                <li aria-hidden="true" className="w-px h-4 bg-[var(--color-ichor-border)]" />
                {opsNav.map((item) => (
                  <li key={item.href}>
                    <Link
                      href={item.href}
                      className="ichor-nav-link text-xs text-[var(--color-ichor-text-faint)]"
                    >
                      {item.label}
                    </Link>
                  </li>
                ))}
              </ul>

              {/* Mobile : drawer trigger */}
              <div className="lg:hidden">
                <MobileNav items={NAV} />
              </div>

              {/* Right cluster : status + push + cmd-K hint */}
              <div className="ml-auto flex items-center gap-3">
                <div className="hidden md:inline-flex items-center gap-1.5 text-[11px] font-mono text-[var(--color-ichor-text-muted)]">
                  <StatusDot tone="live" pulse label="LIVE" />
                </div>
                <span
                  className="hidden md:inline-flex items-center gap-1 text-[10px] text-[var(--color-ichor-text-faint)]"
                  title="? pour les raccourcis · Cmd+K pour la palette"
                >
                  <kbd className="ichor-kbd">⌘K</kbd>
                  <kbd className="ichor-kbd">?</kbd>
                </span>
                <PushToggle />
              </div>
            </nav>
          </div>
        </header>

        <main id="main" className="flex-1 relative">
          {children}
        </main>

        <footer className="border-t border-[var(--color-ichor-border)] bg-[var(--color-ichor-deep)]/60 backdrop-blur">
          <div className="max-w-7xl mx-auto px-4 py-4 flex flex-wrap items-baseline justify-between gap-3">
            <DisclaimerBanner />
            <span className="text-[10px] font-mono text-[var(--color-ichor-text-faint)]">
              ICHOR · Phase 1 · Voie D · Max 20x
            </span>
          </div>
        </footer>
      </body>
    </html>
  );
}
