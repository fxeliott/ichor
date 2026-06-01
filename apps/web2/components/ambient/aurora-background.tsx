/**
 * Aurora-cobalt ambient backdrop — the signature "noir + bleu lumineux"
 * atmosphere. Pure CSS (no client JS), GPU-friendly (transform/opacity only),
 * and reduced-motion safe : the drift keyframes are neutralised by the global
 * `prefers-reduced-motion` rule in globals.css + the explicit guard.
 *
 * Mounted ONCE in the root layout, behind all content (z-index:-1). The blobs
 * live inside a `position:fixed; overflow:hidden` field so they never create a
 * scrollbar or overlap interactive content.
 */
export function AuroraBackground() {
  return (
    <div className="aurora-field" aria-hidden>
      <div className="aurora-blob aurora-blob--1" />
      <div className="aurora-blob aurora-blob--2" />
      <div className="aurora-blob aurora-blob--3" />
      <div className="aurora-grid" />
      <div className="aurora-vignette" />
      <div className="aurora-grain" />
    </div>
  );
}
