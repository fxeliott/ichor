/**
 * KeyboardShortcuts — modal triggered by `?` key.
 *
 * Shows the full list of keyboard bindings available across the app :
 * Cmd+K palette, ↑↓ navigation, Esc dismissal, page-specific shortcuts.
 * Mirrors Linear / Vercel / Bloomberg-style power-user surfaces.
 */

"use client";

import * as React from "react";
import { motion, AnimatePresence } from "motion/react";

interface Binding {
  keys: string[];
  label: string;
}

const GLOBAL: Binding[] = [
  { keys: ["⌘", "K"], label: "Ouvrir command palette" },
  { keys: ["?"], label: "Afficher cette aide" },
  { keys: ["Esc"], label: "Fermer modal / dismiss toasts" },
  { keys: ["↑", "↓"], label: "Naviguer suggestions palette" },
  { keys: ["Enter"], label: "Exécuter sélection palette" },
  { keys: ["Tab"], label: "Naviguer focus" },
];

const NAV: Binding[] = [
  { keys: ["G", "H"], label: "Aller à l'accueil" },
  { keys: ["G", "C"], label: "Aller à /confluence" },
  { keys: ["G", "M"], label: "Aller à /macro-pulse" },
  { keys: ["G", "S"], label: "Aller à /sessions" },
  { keys: ["G", "L"], label: "Aller à /learn" },
];

export const KeyboardShortcutsModal: React.FC = () => {
  const [open, setOpen] = React.useState(false);
  const [pendingG, setPendingG] = React.useState(false);

  React.useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      // Don't fire when typing in inputs / textareas / contenteditable
      const target = e.target as HTMLElement;
      const inEditable =
        target.tagName === "INPUT" ||
        target.tagName === "TEXTAREA" ||
        target.isContentEditable;
      if (inEditable && e.key !== "Escape") return;

      if (e.key === "?" && !e.metaKey && !e.ctrlKey) {
        e.preventDefault();
        setOpen((p) => !p);
      } else if (e.key === "Escape") {
        setOpen(false);
        setPendingG(false);
      } else if (e.key === "g" || e.key === "G") {
        setPendingG(true);
        // Reset after 1s if no follow-up
        setTimeout(() => setPendingG(false), 1000);
      } else if (pendingG && !e.metaKey && !e.ctrlKey) {
        setPendingG(false);
        const k = e.key.toLowerCase();
        const map: Record<string, string> = {
          h: "/",
          c: "/confluence",
          m: "/macro-pulse",
          s: "/sessions",
          l: "/learn",
        };
        if (map[k]) {
          e.preventDefault();
          window.location.href = map[k];
        }
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [pendingG]);

  return (
    <AnimatePresence>
      {open ? (
        <motion.div
          role="dialog"
          aria-modal="true"
          aria-label="Raccourcis clavier"
          className="fixed inset-0 z-50 flex items-center justify-center p-4"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
        >
          <button
            type="button"
            aria-label="Fermer"
            onClick={() => setOpen(false)}
            className="absolute inset-0 bg-[var(--color-ichor-deep)]/85 backdrop-blur-sm cursor-default"
          />
          <motion.div
            className="relative w-full max-w-xl ichor-glass rounded-xl ichor-glow"
            initial={{ scale: 0.96, y: 8 }}
            animate={{ scale: 1, y: 0 }}
            exit={{ scale: 0.96, y: 8 }}
            transition={{ duration: 0.18, ease: [0.16, 1, 0.3, 1] }}
          >
            <header className="flex items-baseline justify-between p-4 border-b border-[var(--color-ichor-border)]">
              <div>
                <h2 className="text-base font-semibold text-[var(--color-ichor-text)]">
                  Raccourcis clavier
                </h2>
                <p className="text-[11px] text-[var(--color-ichor-text-subtle)]">
                  Press <kbd className="ichor-kbd">?</kbd> à tout moment pour afficher.
                </p>
              </div>
              <button
                type="button"
                onClick={() => setOpen(false)}
                className="text-[var(--color-ichor-text-faint)] hover:text-[var(--color-ichor-text)] text-xl leading-none"
                aria-label="Fermer"
              >
                ×
              </button>
            </header>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-1 p-4">
              <Section title="Global" bindings={GLOBAL} />
              <Section title="Navigation (G + ...)" bindings={NAV} />
            </div>

            <footer className="px-4 py-3 border-t border-[var(--color-ichor-border)] text-[11px] text-[var(--color-ichor-text-subtle)]">
              Tip : <kbd className="ichor-kbd">G</kbd> puis{" "}
              <kbd className="ichor-kbd">C</kbd> ouvre /confluence ; appuie{" "}
              <kbd className="ichor-kbd">G</kbd> seul puis attends 1s pour annuler.
            </footer>
          </motion.div>
        </motion.div>
      ) : null}
    </AnimatePresence>
  );
};

function Section({
  title,
  bindings,
}: {
  title: string;
  bindings: Binding[];
}) {
  return (
    <div>
      <h3 className="text-[10px] uppercase tracking-wider text-[var(--color-ichor-text-faint)] font-mono mb-2">
        {title}
      </h3>
      <ul className="space-y-1.5">
        {bindings.map((b, i) => (
          <li
            key={i}
            className="flex items-center justify-between gap-3 text-xs"
          >
            <span className="text-[var(--color-ichor-text-muted)]">
              {b.label}
            </span>
            <span className="flex items-center gap-1">
              {b.keys.map((k, j) => (
                <kbd key={j} className="ichor-kbd">
                  {k}
                </kbd>
              ))}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
