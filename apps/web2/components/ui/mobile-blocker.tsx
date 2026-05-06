// MobileBlocker — affiché sur drill-downs profonds quand viewport est trop
// étroit pour rester utile (knowledge-graph, time-machine replay, scenarios
// compare 3-col). Cf SPEC.md §3.6 + DESIGN §8.
//
// Pas de "responsive design qui fait semblant" : on bloque proprement avec
// un message clair + 2 actions (email-self + copy-link).

"use client";

import * as Dialog from "@radix-ui/react-dialog";
import { useState } from "react";
import { cn } from "@/lib/cn";

export interface MobileBlockerProps {
  feature: string; // human-readable: "le knowledge graph"
  currentUrl: string;
  userEmail?: string;
  open?: boolean;
  onDismiss?: () => void;
  className?: string;
}

export function MobileBlocker({
  feature,
  currentUrl,
  userEmail,
  open = true,
  onDismiss,
  className,
}: MobileBlockerProps) {
  const [copied, setCopied] = useState(false);

  const mailto =
    `mailto:${userEmail ?? ""}` +
    `?subject=${encodeURIComponent("Ouvrir Ichor sur desktop")}` +
    `&body=${encodeURIComponent(currentUrl)}`;

  const onCopy = async () => {
    try {
      await navigator.clipboard.writeText(currentUrl);
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    } catch {
      // clipboard unavailable — silent
    }
  };

  return (
    <Dialog.Root open={open} onOpenChange={(o) => !o && onDismiss?.()}>
      <Dialog.Portal>
        <Dialog.Overlay
          className={cn("fixed inset-0 z-[400] bg-[rgba(4,7,12,0.72)] backdrop-blur-sm")}
        />
        <Dialog.Content
          className={cn(
            "fixed left-1/2 top-1/2 z-[410] w-[min(92vw,420px)] -translate-x-1/2 -translate-y-1/2",
            "rounded-xl border border-[var(--color-border-strong)] bg-[var(--color-bg-elevated)] p-6 shadow-[var(--shadow-lg)]",
            className,
          )}
          aria-describedby="mb-description"
        >
          <Dialog.Title
            data-editorial
            className="text-2xl tracking-tight text-[var(--color-text-primary)]"
          >
            Best on desktop
          </Dialog.Title>
          <Dialog.Description
            id="mb-description"
            className="mt-2 text-sm leading-relaxed text-[var(--color-text-secondary)]"
          >
            <strong className="text-[var(--color-text-primary)]">{feature}</strong> a besoin de plus
            d&apos;espace écran pour rester lisible. La densité d&apos;information le rendrait
            illisible sur mobile.
          </Dialog.Description>

          <div className="mt-5 flex flex-col gap-2">
            <a
              href={mailto}
              className="flex items-center justify-center rounded-md bg-[var(--color-accent-cobalt)] px-4 py-2.5 text-sm font-medium text-white transition-opacity hover:opacity-90 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-bull)]"
            >
              M&apos;envoyer le lien par email
            </a>
            <button
              type="button"
              onClick={onCopy}
              className="flex items-center justify-center rounded-md border border-[var(--color-border-default)] bg-transparent px-4 py-2.5 text-sm font-medium text-[var(--color-text-primary)] transition-colors hover:border-[var(--color-border-strong)] hover:bg-[var(--color-bg-surface)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-bull)]"
            >
              {copied ? "Lien copié !" : "Copier le lien"}
            </button>
            {onDismiss && (
              <Dialog.Close asChild>
                <button
                  type="button"
                  className="mt-1 text-xs text-[var(--color-text-muted)] hover:text-[var(--color-text-secondary)]"
                >
                  Continuer quand même
                </button>
              </Dialog.Close>
            )}
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
