import type { Metadata, Viewport } from "next";
import Link from "next/link";
import { DisclaimerBanner } from "@ichor/ui";
import { LiveEventsToast } from "./live-events-toast";
import { ServiceWorkerRegister } from "./service-worker-register";
import "./globals.css";

export const metadata: Metadata = {
  title: { default: "Ichor", template: "%s · Ichor" },
  description: "Autonomous market intelligence — Phase 0",
  applicationName: "Ichor",
  robots: { index: false, follow: false }, // pre-launch: keep out of search engines
  manifest: "/manifest.webmanifest",
};

export const viewport: Viewport = {
  themeColor: "#0a0a0b",
  colorScheme: "dark",
  width: "device-width",
  initialScale: 1,
};

const NAV: { href: string; label: string }[] = [
  { href: "/", label: "Aujourd'hui" },
  { href: "/sessions", label: "Sessions" },
  { href: "/briefings", label: "Briefings" },
  { href: "/assets", label: "Actifs" },
  { href: "/alerts", label: "Alertes" },
  { href: "/news", label: "News" },
  { href: "/calibration", label: "Calibration" },
];

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="fr">
      <body className="bg-neutral-950 text-neutral-100 antialiased min-h-screen flex flex-col">
        {/* WCAG 2.4.1 — Skip to main content for keyboard users. The link is
            visually hidden until it receives focus. */}
        <a
          href="#main"
          className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-50 focus:px-3 focus:py-1.5 focus:rounded focus:bg-emerald-600 focus:text-neutral-50"
        >
          Aller au contenu principal
        </a>
        <ServiceWorkerRegister />
        <LiveEventsToast />
        <DisclaimerBanner compact />

        <header className="border-b border-neutral-800 bg-neutral-950/80 backdrop-blur sticky top-0 z-10">
          <nav
            className="max-w-6xl mx-auto px-4 py-3 flex items-center gap-6"
            aria-label="Navigation principale"
          >
            <Link
              href="/"
              className="flex items-center gap-2 text-neutral-100 hover:text-emerald-300 transition"
            >
              <svg
                width="22"
                height="14"
                viewBox="0 0 50 28"
                aria-hidden="true"
                className="opacity-90"
              >
                <path
                  d="M3 22 L13 6 L21 18 L29 4 L41 22"
                  stroke="currentColor"
                  strokeWidth="2"
                  fill="none"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
                <circle cx="41" cy="22" r="2" fill="currentColor" />
              </svg>
              <span className="text-base font-semibold tracking-tight">Ichor</span>
            </Link>
            <ul className="flex items-center gap-4 text-sm text-neutral-400">
              {NAV.map((item) => (
                <li key={item.href}>
                  <Link
                    href={item.href}
                    className="hover:text-neutral-100 transition"
                  >
                    {item.label}
                  </Link>
                </li>
              ))}
            </ul>
            <span className="ml-auto text-[11px] text-neutral-400 font-mono">
              Phase 0
            </span>
          </nav>
        </header>

        <div id="main" className="flex-1">{children}</div>

        <footer className="border-t border-neutral-800 bg-neutral-950/80">
          <div className="max-w-6xl mx-auto px-4 py-4">
            <DisclaimerBanner />
          </div>
        </footer>
      </body>
    </html>
  );
}
