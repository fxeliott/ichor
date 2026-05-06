// BiasIndicator — fondement §14 du design system Ichor.
//
// Tout affichage chiffré de bias (long/short/neutral) DOIT passer par ce
// composant. Il satisfait WCAG 1.4.1 (use of color) par redondance triple
// non-négociable :
//
//   couleur (vert/rouge/neutral)  +  signe (+/−/±)  +  glyphe (▲/▼/━)
//
// Le composant est un présentational pur. Le parent calcule `bias` à
// partir de la value selon ses propres seuils (e.g. ±0.1pp = neutral).
// Le composant ne fait *pas* de heuristique sur la value pour deviner
// le bias — il fait confiance au prop.

import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/cn";

const variants = cva(
  "inline-flex items-baseline whitespace-nowrap font-mono leading-none transition-opacity duration-[var(--duration-fast)]",
  {
    variants: {
      size: {
        xs: "gap-1 text-[10px]",
        sm: "gap-1 text-xs",
        md: "gap-1.5 text-sm",
        lg: "gap-2 text-base",
        xl: "gap-2 text-2xl",
      },
      bias: {
        bull: "text-[var(--color-bull)]",
        bear: "text-[var(--color-bear)]",
        neutral: "text-[var(--color-neutral)]",
      },
      withGlow: {
        true: "",
        false: "",
      },
    },
    compoundVariants: [
      {
        bias: "bull",
        withGlow: true,
        className: "[filter:drop-shadow(var(--shadow-glow-bull))]",
      },
      {
        bias: "bear",
        withGlow: true,
        className: "[filter:drop-shadow(var(--shadow-glow-bear))]",
      },
    ],
    defaultVariants: {
      size: "md",
      withGlow: false,
    },
  },
);

type Bias = "bull" | "bear" | "neutral";

export interface BiasIndicatorProps extends Omit<
  VariantProps<typeof variants>,
  "bias" | "size" | "withGlow"
> {
  bias: Bias;
  value: number;
  unit?: "%" | "pp" | "bps";
  magnitude?: { low: number; high: number };
  magnitudeUnit?: "pips" | "bps" | "%";
  variant?: "compact" | "default" | "large";
  size?: "xs" | "sm" | "md" | "lg" | "xl";
  withGlow?: boolean;
  precision?: number;
  className?: string;
  ariaLabel?: string;
}

const GLYPHS: Record<Bias, string> = {
  bull: "▲",
  bear: "▼",
  neutral: "━",
};

// U+2212 (MINUS SIGN), wider/heavier than ASCII hyphen-minus — better
// visual weight for financial data.
const SIGNS: Record<Bias, string> = {
  bull: "+",
  bear: "−",
  neutral: "±",
};

const BIAS_NAMES: Record<Bias, string> = {
  bull: "Bullish",
  bear: "Bearish",
  neutral: "Neutral",
};

export function BiasIndicator({
  bias,
  value,
  unit = "%",
  magnitude,
  magnitudeUnit = "pips",
  variant = "default",
  size = "md",
  withGlow = false,
  precision = 2,
  className,
  ariaLabel,
}: BiasIndicatorProps) {
  const absValue = Math.abs(value);
  // Tiny values: render `~0` to avoid misleading "0.00%" precision.
  const valueLabel = absValue < 0.05 ? "~0" : absValue.toFixed(precision);

  const computedAriaLabel =
    ariaLabel ??
    [
      BIAS_NAMES[bias],
      `${SIGNS[bias]}${valueLabel}${unit}`,
      magnitude ? `magnitude ${magnitude.low}–${magnitude.high} ${magnitudeUnit}` : null,
    ]
      .filter(Boolean)
      .join(", ");

  return (
    <span
      role="img"
      aria-label={computedAriaLabel}
      data-bias={bias}
      data-variant={variant}
      className={cn(variants({ size, bias, withGlow }), className)}
    >
      <span aria-hidden="true">{GLYPHS[bias]}</span>
      <span className="tabular-nums">
        <span aria-hidden="true">{SIGNS[bias]}</span>
        {valueLabel}
        <span className="text-[0.85em] opacity-80">{unit}</span>
      </span>
      {magnitude && variant !== "compact" && (
        <span
          aria-hidden="true"
          className="tabular-nums text-[var(--color-text-muted)] text-[0.85em]"
        >
          {magnitude.low}–{magnitude.high} {magnitudeUnit}
        </span>
      )}
    </span>
  );
}
