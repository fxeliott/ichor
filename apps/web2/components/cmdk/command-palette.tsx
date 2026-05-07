// CommandPalette — global Cmd+K (or Ctrl+K) navigation surface for
// Ichor web2 (Phase A.9.5). Pattern : Bloomberg-style ticker→action
// flow, but adapted to a single-user pre-trade research dashboard.
//
// Mount once in app/layout.tsx. Listens globally for Cmd/Ctrl+K and
// toggles. Uses Radix Dialog for focus-trap + ESC dismiss + ARIA roles.
//
// Action set kept narrow on purpose : the 41 routes are too many to
// list flat, so the palette mirrors the TopNav grouping but with
// inline keyboard nav (cmdk handles ↑/↓/Enter natively).

"use client";

import * as Dialog from "@radix-ui/react-dialog";
import { Command } from "cmdk";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

interface PaletteAction {
  id: string;
  label: string;
  group: string;
  href: string;
  /** Short keyword string to bias matching (e.g. ticker aliases). */
  keywords?: string;
}

const ACTIONS: PaletteAction[] = [
  // Live
  { id: "today", label: "Today — pre-session checklist", group: "Live", href: "/today" },
  { id: "sessions", label: "Sessions — index", group: "Live", href: "/sessions" },
  { id: "macro-pulse", label: "Macro pulse", group: "Live", href: "/macro-pulse" },
  // Per-asset shortcuts (most common Eliot flow)
  {
    id: "session-eur",
    label: "Session — EUR/USD",
    group: "Asset",
    href: "/sessions/EUR_USD",
    keywords: "eurusd eur usd euro dollar",
  },
  {
    id: "session-jpy",
    label: "Session — USD/JPY",
    group: "Asset",
    href: "/sessions/USD_JPY",
    keywords: "usdjpy yen carry intervention",
  },
  {
    id: "session-gbp",
    label: "Session — GBP/USD",
    group: "Asset",
    href: "/sessions/GBP_USD",
    keywords: "gbpusd cable boe sterling",
  },
  {
    id: "session-aud",
    label: "Session — AUD/USD",
    group: "Asset",
    href: "/sessions/AUD_USD",
    keywords: "audusd aussie rba commodity",
  },
  {
    id: "session-cad",
    label: "Session — USD/CAD",
    group: "Asset",
    href: "/sessions/USD_CAD",
    keywords: "usdcad loonie boc oil",
  },
  {
    id: "session-xau",
    label: "Session — Gold (XAU/USD)",
    group: "Asset",
    href: "/sessions/XAU_USD",
    keywords: "xauusd gold or real yields",
  },
  {
    id: "session-spx",
    label: "Session — S&P 500 (SPX500)",
    group: "Asset",
    href: "/sessions/SPX500_USD",
    keywords: "spx s&p 500 us equity",
  },
  {
    id: "session-nas",
    label: "Session — Nasdaq 100 (NAS100)",
    group: "Asset",
    href: "/sessions/NAS100_USD",
    keywords: "nas100 nasdaq tech mag7",
  },
  // Analyse
  { id: "confluence", label: "Confluence factors", group: "Analyse", href: "/confluence" },
  { id: "correlations", label: "Cross-asset correlations", group: "Analyse", href: "/correlations" },
  { id: "yield-curve", label: "Yield curve", group: "Analyse", href: "/yield-curve" },
  {
    id: "knowledge-graph",
    label: "Knowledge graph",
    group: "Analyse",
    href: "/knowledge-graph",
    keywords: "graph causal kg",
  },
  // Surveillance
  { id: "alerts", label: "Alerts dashboard", group: "Surveillance", href: "/alerts" },
  { id: "news", label: "News feed", group: "Surveillance", href: "/news" },
  { id: "narratives", label: "Narratives tracker", group: "Surveillance", href: "/narratives" },
  { id: "geopolitics", label: "Geopolitics", group: "Surveillance", href: "/geopolitics" },
  {
    id: "polymarket",
    label: "Polymarket / Kalshi divergence",
    group: "Surveillance",
    href: "/polymarket",
  },
  // Calibration
  { id: "calibration", label: "Brier calibration", group: "Calibration", href: "/calibration" },
  { id: "post-mortems", label: "Post-mortems", group: "Calibration", href: "/post-mortems" },
  { id: "sources", label: "Sources health", group: "Calibration", href: "/sources" },
  { id: "admin", label: "Admin pipeline-health", group: "Calibration", href: "/admin" },
  // Learn
  {
    id: "learn",
    label: "Learn — index",
    group: "Learn",
    href: "/learn",
    keywords: "doc methodology",
  },
  {
    id: "glossary",
    label: "Glossary",
    group: "Learn",
    href: "/learn/glossary",
    keywords: "definition terms",
  },
];

const GROUPS_ORDER = ["Live", "Asset", "Analyse", "Surveillance", "Calibration", "Learn"];

export function CommandPalette() {
  const router = useRouter();
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((o) => !o);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const navigate = (href: string) => {
    setOpen(false);
    router.push(href);
  };

  return (
    <Dialog.Root open={open} onOpenChange={setOpen}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-[200] bg-[rgba(4,7,12,0.72)] backdrop-blur-sm" />
        <Dialog.Content
          aria-label="Palette de commandes"
          className="fixed left-1/2 top-[20%] z-[210] w-[min(92vw,640px)] -translate-x-1/2 overflow-hidden rounded-xl border border-[var(--color-border-strong)] bg-[var(--color-bg-elevated)] shadow-[var(--shadow-lg)]"
        >
          <Dialog.Title className="sr-only">Palette de commandes Ichor</Dialog.Title>
          <Command label="Palette de commandes Ichor" loop>
            <Command.Input
              placeholder="Aller à un actif, une route, ou une action..."
              className="w-full border-b border-[var(--color-border-default)] bg-transparent px-4 py-3 text-sm text-[var(--color-text-primary)] outline-none placeholder:text-[var(--color-text-muted)]"
            />
            <Command.List className="max-h-[60vh] overflow-y-auto p-2">
              <Command.Empty className="px-3 py-6 text-center text-xs text-[var(--color-text-muted)]">
                Aucune action correspondante.
              </Command.Empty>
              {GROUPS_ORDER.map((g) => {
                const groupActions = ACTIONS.filter((a) => a.group === g);
                if (groupActions.length === 0) return null;
                return (
                  <Command.Group
                    key={g}
                    heading={g}
                    className="mb-1 px-1 [&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:py-1 [&_[cmdk-group-heading]]:text-[10px] [&_[cmdk-group-heading]]:uppercase [&_[cmdk-group-heading]]:tracking-wider [&_[cmdk-group-heading]]:text-[var(--color-text-muted)]"
                  >
                    {groupActions.map((a) => (
                      <Command.Item
                        key={a.id}
                        value={`${a.label} ${a.keywords ?? ""}`}
                        onSelect={() => navigate(a.href)}
                        className="flex cursor-pointer items-center justify-between rounded-md px-3 py-2 text-sm text-[var(--color-text-secondary)] aria-selected:bg-[var(--color-bg-overlay)] aria-selected:text-[var(--color-text-primary)] data-[selected=true]:bg-[var(--color-bg-overlay)] data-[selected=true]:text-[var(--color-text-primary)]"
                      >
                        <span>{a.label}</span>
                        <span className="font-mono text-[10px] text-[var(--color-text-muted)]">
                          {a.href}
                        </span>
                      </Command.Item>
                    ))}
                  </Command.Group>
                );
              })}
            </Command.List>
            <div className="flex items-center justify-between border-t border-[var(--color-border-default)] px-3 py-2 text-[10px] text-[var(--color-text-muted)]">
              <span>↑↓ naviguer · ↵ ouvrir · esc fermer</span>
              <span className="font-mono">⌘K / Ctrl+K</span>
            </div>
          </Command>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
