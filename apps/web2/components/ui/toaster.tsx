// Toaster — global notification surface for Ichor web2 (Phase A.9.3).
//
// Wraps `sonner` with the Ichor design tokens (dark, cobalt accent,
// reduced-motion respect). Mount once in app/layout.tsx ; emit toasts
// from anywhere via `import { toast } from "sonner"`.
//
// Style : right-bottom, opaque enough to read on data-dense panels,
// borderline severe (so a toast gets noticed without being noisy).

"use client";

import { Toaster as SonnerToaster } from "sonner";

export function Toaster() {
  return (
    <SonnerToaster
      position="bottom-right"
      theme="dark"
      richColors
      closeButton
      duration={4500}
      gap={10}
      visibleToasts={4}
      toastOptions={{
        // Map sonner's classed shell to Ichor tokens. We can't fully
        // override sonner's internal CSS without unstyled mode, so we
        // tighten the surface look here.
        classNames: {
          toast:
            "!bg-[var(--color-bg-elevated)] !text-[var(--color-text-primary)] !border-[var(--color-border-default)] !shadow-[var(--shadow-lg)] !font-sans",
          description: "!text-[var(--color-text-secondary)]",
          actionButton: "!bg-[var(--color-accent-cobalt)] !text-white",
          cancelButton:
            "!bg-transparent !text-[var(--color-text-muted)] !border !border-[var(--color-border-default)]",
        },
      }}
    />
  );
}
