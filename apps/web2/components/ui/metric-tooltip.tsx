// MetricTooltip — pédagogie ultra-explicative §3.5.
//
// S'attache à tout terme technique (Brier, VPIN, GEX, IORB, OAS, etc.) et
// ouvre une popover Radix avec définition courte + lien optionnel vers
// `/learn/glossary#<anchor>`.
//
// Trigger : hover (200ms delay open / 80ms close — DESIGN §5) + focus
// keyboard (Enter/Space). Esc ferme. Pas de focus trap (tooltip ≠ dialog).

"use client";

import * as Tooltip from "@radix-ui/react-tooltip";
import Link from "next/link";
import { cn } from "@/lib/cn";

export interface MetricTooltipProps {
  term: string;
  title?: string;
  definition: string;
  glossaryAnchor?: string;
  side?: "top" | "right" | "bottom" | "left";
  delayDuration?: number;
  density?: "compact" | "comfortable";
  children?: React.ReactNode;
  className?: string;
}

export function MetricTooltip({
  term,
  title,
  definition,
  glossaryAnchor,
  side = "top",
  delayDuration = 200,
  density = "comfortable",
  children,
  className,
}: MetricTooltipProps) {
  return (
    <Tooltip.Provider delayDuration={delayDuration} skipDelayDuration={500}>
      <Tooltip.Root>
        <Tooltip.Trigger asChild>
          <button
            type="button"
            className={cn(
              "inline cursor-help underline decoration-dotted decoration-[var(--color-text-muted)] underline-offset-2 transition-colors duration-[var(--duration-fast)] hover:decoration-[var(--color-text-secondary)] focus-visible:decoration-[var(--color-bull)]",
              density === "compact" && "decoration-1",
              className,
            )}
          >
            {children ?? term}
          </button>
        </Tooltip.Trigger>
        <Tooltip.Portal>
          <Tooltip.Content
            side={side}
            sideOffset={6}
            collisionPadding={8}
            className={cn(
              "z-[500] max-w-xs rounded-md border border-[var(--color-border-strong)] bg-[var(--color-bg-elevated)] p-3 text-sm",
              "shadow-[var(--shadow-md)]",
            )}
          >
            <h4 className="mb-1 font-semibold text-[var(--color-text-primary)]">{title ?? term}</h4>
            <p className="text-[var(--color-text-secondary)]">{definition}</p>
            {glossaryAnchor && (
              <Link
                href={`/learn/glossary#${glossaryAnchor}`}
                className="mt-2 inline-flex items-center gap-1 text-xs text-[var(--color-accent-cobalt-bright)] hover:underline"
              >
                Voir le glossaire →
              </Link>
            )}
            <Tooltip.Arrow className="fill-[var(--color-bg-elevated)]" />
          </Tooltip.Content>
        </Tooltip.Portal>
      </Tooltip.Root>
    </Tooltip.Provider>
  );
}
