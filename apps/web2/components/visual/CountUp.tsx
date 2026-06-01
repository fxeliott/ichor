"use client";

import { animate, m, useMotionValue, useTransform } from "motion/react";
import { useEffect } from "react";

/**
 * CountUp — animates a number from 0 to `value` on mount (verified motion
 * pattern : useMotionValue + animate + useTransform formatter rendered in an
 * m.span). Respects prefers-reduced-motion (sets the final value instantly).
 *
 * Refonte 2026 — gives the big stat numbers a premium "alive" entrance.
 */
export function CountUp({
  value,
  decimals = 0,
  prefix = "",
  suffix = "",
  duration = 1.2,
}: {
  value: number;
  decimals?: number;
  prefix?: string;
  suffix?: string;
  duration?: number;
}) {
  const mv = useMotionValue(0);
  const text = useTransform(mv, (v) => {
    const n = decimals > 0 ? v.toFixed(decimals) : Math.round(v).toLocaleString("fr-FR");
    return `${prefix}${n}${suffix}`;
  });

  useEffect(() => {
    const reduce =
      typeof window !== "undefined" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduce) {
      mv.set(value);
      return;
    }
    const controls = animate(mv, value, { duration, ease: [0.2, 0, 0, 1] });
    return () => controls.stop();
    // mv is a stable MotionValue ref
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value, duration]);

  return <m.span>{text}</m.span>;
}
