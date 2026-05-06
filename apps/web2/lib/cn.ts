// Tailwind class-merge helper. Used by all UI components to compose
// `className` props with the design-system defaults. clsx handles
// conditionals + arrays; tailwind-merge resolves conflicting utilities
// (e.g. `p-2 p-4` → `p-4`).

import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}
