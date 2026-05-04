/**
 * MobileNav — slide-in drawer for screens < lg (1024px).
 *
 * Triggered by hamburger button. Shows the same nav items as the desktop
 * header but full-screen with bigger tap targets.
 */

"use client";

import * as React from "react";
import Link from "next/link";
import { motion, AnimatePresence } from "motion/react";

interface NavItem {
  href: string;
  label: string;
  group: "core" | "macro" | "ops";
}

export function MobileNav({ items }: { items: NavItem[] }) {
  const [open, setOpen] = React.useState(false);

  const close = React.useCallback(() => setOpen(false), []);

  // Close on Escape
  React.useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape" && open) close();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [close, open]);

  // Lock body scroll when drawer open
  React.useEffect(() => {
    if (open) {
      const prev = document.body.style.overflow;
      document.body.style.overflow = "hidden";
      return () => {
        document.body.style.overflow = prev;
      };
    }
  }, [open]);

  const groups = {
    core: items.filter((i) => i.group === "core"),
    macro: items.filter((i) => i.group === "macro"),
    ops: items.filter((i) => i.group === "ops"),
  };

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="lg:hidden inline-flex items-center justify-center w-9 h-9 rounded-md border border-[var(--color-ichor-border)] bg-[var(--color-ichor-surface)] hover:border-[var(--color-ichor-accent)] transition"
        aria-label="Ouvrir le menu de navigation"
        aria-expanded={open}
      >
        <svg
          width="16"
          height="16"
          viewBox="0 0 16 16"
          fill="none"
          aria-hidden="true"
          className="text-[var(--color-ichor-text-muted)]"
        >
          <line x1="2" y1="4" x2="14" y2="4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
          <line x1="2" y1="8" x2="14" y2="8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
          <line x1="2" y1="12" x2="14" y2="12" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
        </svg>
      </button>

      <AnimatePresence>
        {open ? (
          <motion.div
            role="dialog"
            aria-modal="true"
            aria-label="Menu de navigation"
            className="fixed inset-0 z-50 lg:hidden"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
          >
            <button
              type="button"
              aria-label="Fermer le menu"
              onClick={close}
              className="absolute inset-0 bg-[var(--color-ichor-deep)]/80 backdrop-blur-sm cursor-default"
            />
            <motion.aside
              className="absolute top-0 left-0 bottom-0 w-72 max-w-[85vw] ichor-glass border-r border-[var(--color-ichor-border)] flex flex-col"
              initial={{ x: "-100%" }}
              animate={{ x: 0 }}
              exit={{ x: "-100%" }}
              transition={{ duration: 0.22, ease: [0.16, 1, 0.3, 1] }}
            >
              <header className="flex items-baseline justify-between p-4 border-b border-[var(--color-ichor-border)]">
                <span className="text-base font-semibold bg-gradient-to-r from-white to-[var(--color-ichor-accent-bright)] bg-clip-text text-transparent">
                  Ichor
                </span>
                <button
                  type="button"
                  onClick={close}
                  className="text-[var(--color-ichor-text-faint)] hover:text-[var(--color-ichor-text)] text-2xl leading-none px-2"
                  aria-label="Fermer"
                >
                  ×
                </button>
              </header>

              <nav className="flex-1 overflow-y-auto p-4 space-y-5">
                <NavGroup title="Core" items={groups.core} onNav={close} />
                <NavGroup title="Macro" items={groups.macro} onNav={close} />
                <NavGroup title="Ops" items={groups.ops} onNav={close} />
              </nav>

              <footer className="p-4 border-t border-[var(--color-ichor-border)]">
                <p className="text-[10px] font-mono text-[var(--color-ichor-text-faint)]">
                  Ichor · Phase 1 · Macro intel
                </p>
              </footer>
            </motion.aside>
          </motion.div>
        ) : null}
      </AnimatePresence>
    </>
  );
}

function NavGroup({
  title,
  items,
  onNav,
}: {
  title: string;
  items: NavItem[];
  onNav: () => void;
}) {
  return (
    <div>
      <h2 className="text-[10px] uppercase tracking-wider text-[var(--color-ichor-text-faint)] font-mono mb-2">
        {title}
      </h2>
      <ul className="space-y-1">
        {items.map((item) => (
          <li key={item.href}>
            <Link
              href={item.href}
              onClick={onNav}
              className="block py-2 px-2 rounded text-sm text-[var(--color-ichor-text-muted)] hover:text-[var(--color-ichor-text)] hover:bg-[var(--color-ichor-surface-2)] transition"
            >
              {item.label}
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
