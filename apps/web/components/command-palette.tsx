/**
 * CommandPalette — Cmd+K / Ctrl+K modal launcher.
 *
 * Linear / Vercel / Bloomberg Terminal vibe : keyboard-first navigation.
 * No external `cmdk` dep — handcrafted with motion + a fuzzy matcher.
 *
 * Bindings :
 *   Cmd/Ctrl + K     toggle palette
 *   Esc              close
 *   ↑ / ↓            navigate suggestions
 *   Enter            execute selected
 *   tab order        natural focus on input → first row
 *
 * Includes :
 *   - Direct page nav (sessions, calibration, narratives, …)
 *   - Asset shortcuts ("EUR/USD" → /sessions/EUR_USD)
 *   - Action commands (refresh, replay, counterfactual, shock)
 *
 * VISION_2026 — Bloomberg Terminal feel.
 */

"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { motion, AnimatePresence } from "motion/react";

type CommandKind = "page" | "asset" | "action";

interface Command {
  id: string;
  label: string;
  hint?: string;
  kind: CommandKind;
  href?: string;
  action?: () => void;
  keywords?: string[];
}

const PAGES: Command[] = [
  { id: "home", label: "Accueil", hint: "/", kind: "page", href: "/" },
  { id: "sessions", label: "Cartes session", hint: "/sessions", kind: "page", href: "/sessions" },
  { id: "confluence", label: "Confluence multi-actifs", hint: "/confluence", kind: "page", href: "/confluence", keywords: ["score", "synthese", "drivers", "trade strength"] },
  { id: "correlations", label: "Corrélations cross-asset", hint: "/correlations", kind: "page", href: "/correlations", keywords: ["matrix", "pearson", "regime"] },
  { id: "narratives", label: "Narratives", hint: "/narratives", kind: "page", href: "/narratives" },
  { id: "kg", label: "Knowledge graph", hint: "/knowledge-graph", kind: "page", href: "/knowledge-graph", keywords: ["graph", "shock", "causal"] },
  { id: "geopol", label: "Géopolitique", hint: "/geopolitics", kind: "page", href: "/geopolitics" },
  { id: "calibration", label: "Calibration", hint: "/calibration", kind: "page", href: "/calibration", keywords: ["brier", "track-record"] },
  { id: "sources", label: "Sources data", hint: "/sources", kind: "page", href: "/sources", keywords: ["feeds", "upstream", "providers"] },
  { id: "admin", label: "Admin", hint: "/admin", kind: "page", href: "/admin", keywords: ["status", "ops", "health"] },
  { id: "briefings", label: "Briefings", hint: "/briefings", kind: "page", href: "/briefings" },
  { id: "alerts", label: "Alertes", hint: "/alerts", kind: "page", href: "/alerts" },
  { id: "news", label: "News", hint: "/news", kind: "page", href: "/news" },
];

const ASSET_LIST: ReadonlyArray<readonly [string, string]> = [
  ["EUR_USD", "EUR/USD"],
  ["GBP_USD", "GBP/USD"],
  ["USD_JPY", "USD/JPY"],
  ["AUD_USD", "AUD/USD"],
  ["USD_CAD", "USD/CAD"],
  ["XAU_USD", "XAU/USD · gold"],
  ["NAS100_USD", "NAS100"],
  ["SPX500_USD", "SPX500"],
] as const;

const ASSETS: Command[] = ASSET_LIST.map(([code, label]) => ({
  id: `asset-${code}`,
  label,
  hint: `Carte session ${code.replace("_", "/")}`,
  kind: "asset" as CommandKind,
  href: `/sessions/${code}`,
  keywords: [code, code.replace("_", "/").toLowerCase()],
}));

const REPLAY_LIST: ReadonlyArray<readonly [string, string]> = [
  ["EUR_USD", "EUR/USD"],
  ["XAU_USD", "XAU/USD"],
  ["USD_JPY", "USD/JPY"],
] as const;

const REPLAY: Command[] = REPLAY_LIST.map(([code, label]) => ({
  id: `replay-${code}`,
  label: `Replay ${label}`,
  hint: `/replay/${code}`,
  kind: "action" as CommandKind,
  href: `/replay/${code}`,
  keywords: ["replay", "time-machine", code],
}));

const SCENARIOS: Command[] = ASSET_LIST.map(([code, label]) => ({
  id: `scen-${code}`,
  label: `Scénarios ${label}`,
  hint: `/scenarios/${code}`,
  kind: "action" as CommandKind,
  href: `/scenarios/${code}`,
  keywords: [
    "scenarios",
    "scenario",
    "rr",
    "trade plan",
    "smc",
    "pivots",
    "pdh",
    "pdl",
    code,
  ],
}));

const HOURLY_VOL: Command[] = ASSET_LIST.map(([code, label]) => ({
  id: `hvol-${code}`,
  label: `Vol horaire ${label}`,
  hint: `/hourly-volatility/${code}`,
  kind: "action" as CommandKind,
  href: `/hourly-volatility/${code}`,
  keywords: ["volatility", "vol", "hour", "best", "moment", "heatmap", code],
}));

const ALL_COMMANDS: Command[] = [
  ...PAGES,
  ...ASSETS,
  ...SCENARIOS,
  ...HOURLY_VOL,
  ...REPLAY,
];

const fuzzyMatch = (q: string, c: Command): number => {
  if (!q) return 1;
  const haystack = [
    c.label.toLowerCase(),
    c.hint?.toLowerCase() ?? "",
    ...(c.keywords ?? []).map((k) => k.toLowerCase()),
  ].join(" ");
  const needle = q.toLowerCase().trim();
  if (haystack.includes(needle)) return 2;
  // letters in order
  let i = 0;
  for (const ch of haystack) {
    if (ch === needle[i]) i++;
    if (i === needle.length) return 1;
  }
  return 0;
};

const KIND_BADGE: Record<CommandKind, { label: string; cls: string }> = {
  page: { label: "page", cls: "bg-sky-900/40 text-sky-300 border-sky-700/40" },
  asset: { label: "actif", cls: "bg-emerald-900/40 text-emerald-300 border-emerald-700/40" },
  action: { label: "action", cls: "bg-amber-900/40 text-amber-300 border-amber-700/40" },
};

export const CommandPalette: React.FC = () => {
  const router = useRouter();
  const [open, setOpen] = React.useState(false);
  const [query, setQuery] = React.useState("");
  const [activeIdx, setActiveIdx] = React.useState(0);
  const inputRef = React.useRef<HTMLInputElement>(null);

  const matches = React.useMemo(() => {
    const scored = ALL_COMMANDS.map((c) => ({ c, s: fuzzyMatch(query, c) }))
      .filter((x) => x.s > 0)
      .sort((a, b) => b.s - a.s);
    return scored.map((x) => x.c).slice(0, 12);
  }, [query]);

  const close = React.useCallback(() => {
    setOpen(false);
    setQuery("");
    setActiveIdx(0);
  }, []);

  // Cmd/Ctrl+K toggle
  React.useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((p) => !p);
      } else if (e.key === "Escape") {
        close();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [close]);

  // Focus input on open
  React.useEffect(() => {
    if (open) {
      requestAnimationFrame(() => inputRef.current?.focus());
    }
  }, [open]);

  const exec = (c: Command) => {
    if (c.href) router.push(c.href);
    if (c.action) c.action();
    close();
  };

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActiveIdx((i) => Math.min(matches.length - 1, i + 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActiveIdx((i) => Math.max(0, i - 1));
    } else if (e.key === "Enter") {
      e.preventDefault();
      const c = matches[activeIdx];
      if (c) exec(c);
    }
  };

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          onClick={close}
          className="fixed inset-0 z-50 flex items-start justify-center pt-24 bg-black/70 backdrop-blur-sm"
        >
          <motion.div
            onClick={(e) => e.stopPropagation()}
            initial={{ scale: 0.96, y: -10 }}
            animate={{ scale: 1, y: 0 }}
            exit={{ scale: 0.96, y: -10 }}
            transition={{ duration: 0.15 }}
            role="dialog"
            aria-label="Command palette"
            className="w-full max-w-xl mx-4 rounded-lg border border-neutral-700 bg-neutral-900 shadow-2xl overflow-hidden"
          >
            <div className="flex items-center gap-2 px-3 py-2 border-b border-neutral-800">
              <span className="text-neutral-500 text-sm" aria-hidden="true">⌘</span>
              <input
                ref={inputRef}
                type="text"
                value={query}
                onChange={(e) => {
                  setQuery(e.target.value);
                  setActiveIdx(0);
                }}
                onKeyDown={onKeyDown}
                placeholder="Tape pour chercher (page, actif, action)…"
                className="flex-1 bg-transparent text-neutral-100 placeholder:text-neutral-500 focus:outline-none text-sm"
                aria-label="Rechercher dans Ichor"
              />
              <kbd className="text-[10px] text-neutral-500 font-mono border border-neutral-700 rounded px-1 py-0.5">
                Esc
              </kbd>
            </div>

            <ul role="listbox" className="max-h-[320px] overflow-y-auto">
              {matches.length === 0 ? (
                <li className="px-3 py-4 text-sm text-neutral-500">
                  Aucun résultat. Essaye « sessions », « EUR/USD », « replay »…
                </li>
              ) : (
                matches.map((c, i) => (
                  <li
                    key={c.id}
                    role="option"
                    aria-selected={i === activeIdx}
                    onMouseEnter={() => setActiveIdx(i)}
                    onClick={() => exec(c)}
                    className={[
                      "flex items-center justify-between gap-2 px-3 py-2 cursor-pointer text-sm",
                      i === activeIdx
                        ? "bg-neutral-800 text-neutral-100"
                        : "text-neutral-300 hover:bg-neutral-800/60",
                    ].join(" ")}
                  >
                    <div className="flex items-center gap-2 min-w-0">
                      <span
                        className={`px-1.5 py-0.5 rounded text-[10px] font-mono border ${KIND_BADGE[c.kind].cls}`}
                      >
                        {KIND_BADGE[c.kind].label}
                      </span>
                      <span className="truncate">{c.label}</span>
                    </div>
                    {c.hint && (
                      <span className="text-[11px] text-neutral-500 font-mono truncate">
                        {c.hint}
                      </span>
                    )}
                  </li>
                ))
              )}
            </ul>

            <footer className="flex items-center justify-between border-t border-neutral-800 bg-neutral-950/40 px-3 py-1.5 text-[10px] text-neutral-500">
              <span className="font-mono">
                <kbd className="border border-neutral-700 rounded px-1">↑</kbd>{" "}
                <kbd className="border border-neutral-700 rounded px-1">↓</kbd>{" "}
                naviguer
              </span>
              <span className="font-mono">
                <kbd className="border border-neutral-700 rounded px-1">↵</kbd>{" "}
                ouvrir
              </span>
              <span className="font-mono">
                <kbd className="border border-neutral-700 rounded px-1">⌘K</kbd>{" "}
                toggle
              </span>
            </footer>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
};
