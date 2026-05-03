# Accessibility audit — Ichor frontend (WCAG 2.2 AA)

**Date:** 2026-05-03  
**Auditor:** Claude (Opus 4.7), automated static review.  
**Scope:** apps/web/app/** + packages/ui/src/components/** (13 components) + shared layout + LiveEventsToast + DisclaimerBanner.  
**Method:** static source inspection, contrast computation against the actual globals.css token palette (sRGB, WCAG 2.x relative-luminance formula, alpha layers blended manually over #0a0a0b), semantic-HTML / ARIA review.  
**Out of scope (NOT verified, see "Limits"):** real screen-reader playback (NVDA/JAWS/VoiceOver), 400 % zoom layout, motor-impairment device testing, axe-core/Lighthouse runtime scans, focus-order in the actually rendered DOM.

Severity legend:

- **BLOCKER** — confirmed WCAG 2.2 AA failure or legal exposure (AMF / EU AI Act). Must be fixed before any external launch.
- **HIGH** — degraded experience for assistive-tech users, breaks a documented WCAG technique, or is a 2.2 new SC borderline (Target Size, Focus Not Obscured, etc.).
- **MEDIUM** — UX improvement that brings a11y closer to "real" usability.
- **LOW** — polish, nice-to-have.

---

## Summary

| Severity | Count |
|----------|-------|
| BLOCKER  | 4     |
| HIGH     | 8     |
| MEDIUM   | 7     |
| LOW      | 3     |

The codebase is in **good shape on the basics** (lang="fr", :focus-visible outline, prefers-reduced-motion, semantic landmarks on most pages, correct contrast on body text). It fails on a recurring small set of issues:

1. **Status pills carry meaning by colour + raw English keyword only** (no accessible name, no SR-friendly translation).
2. **The whole layered-Link → AssetCard pattern is a focus / role landmine** (button-inside-link risk, double accessible name).
3. **LiveEventsToast is announced as silent** — no aria-live, no role=status, no keyboard escape.
4. **WCAG 2.2 SC 2.5.8 Target Size (Minimum) is violated** in several touch targets (toast ×, AlertChip ✓, RegimeIndicator coloured strip).
5. **No "skip to main content" link**, although nav is sticky.
6. **Form labels use the implicit-wrap pattern correctly, but the asset code <input pattern> triggers a browser error tooltip with no accessible custom message** (SC 3.3.1, 3.3.3).

---

## BLOCKER — 4 findings

### B1 — text-neutral-600 body text fails contrast 4.5:1
**WCAG 2.2 SC 1.4.3 (Contrast Minimum)** — measured **2.53:1** against #0a0a0b, required ≥ 4.5:1.

Affected (non-exhaustive):

- apps/web/app/page.tsx:189 — text-[11px] text-neutral-600 paragraph "Prix temps réel non encore connectés…". 11 px is **normal** text in WCAG terms, the 18 pt / 14 pt-bold large-text exemption does NOT apply. Currently invisible to anyone over 40, anyone in daylight, anyone on a low-end IPS panel.
- apps/web/app/layout.tsx:84 — text-[11px] text-neutral-600 "Phase 0" badge in the header. Same problem.
- apps/web/app/assets/[code]/page.tsx:213 — text-[11px] text-neutral-600 "Probabilités issues du dernier viterbi forward pass HMM 3-states…".
- apps/web/app/alerts/page.tsx:203 — text-neutral-600 on the ack timestamp for already-acknowledged alerts; bump it too.

**Fix:** promote every text-neutral-600 used on body or caption text to text-neutral-400 (7.85:1, AA-pass) or text-neutral-500 if the surface is non-essential and ≥ 14 pt. text-neutral-600 should be reserved for decorative borders / dividers, never text.

```tsx
// apps/web/app/page.tsx:189
- <p className="mt-3 text-[11px] text-neutral-600">
+ <p className="mt-3 text-[11px] text-neutral-400">
    Prix temps réel non encore connectés (W2 OANDA pending). Les biais
    proviennent du dernier bias_aggregator run.
  </p>
```

```tsx
// apps/web/app/layout.tsx:83-85
- <span className="ml-auto text-[11px] text-neutral-600 font-mono">
+ <span className="ml-auto text-[11px] text-neutral-400 font-mono">
    Phase 0
  </span>
```

```tsx
// apps/web/app/assets/[code]/page.tsx:213-216
- <p className="mt-2 text-[11px] text-neutral-600">
+ <p className="mt-2 text-[11px] text-neutral-400">
```

---

### B2 — Briefing-list status badge & alert-row meta rely on raw English keyword + color only
**WCAG 2.2 SC 1.1.1 (Non-text Content), SC 1.4.1 (Use of Color), SC 3.1.1 (Language of Page = fr)**

The page is declared lang="fr", but the content surfaces machine values straight from the API:

- apps/web/app/page.tsx:138-148 and apps/web/app/briefings/page.tsx:153-160: render b.status directly (pending, claude_running, completed, failed). For an SR user the dot has no aria-label, the colored pill has no role, and the "completed/failed" English string is announced inside a French sentence flow — confusing AND it conveys the success/failure dichotomy by colour alone (red vs emerald).
- apps/web/app/briefings/page.tsx:151 similarly renders b.briefing_type raw (pre_londres, ny_close…) instead of the human-readable TYPE_LABELS map already defined in page.tsx. Bilingual machine codes leak to the user.
- apps/web/app/alerts/page.tsx:87-95: severity counters show "critical 5 / warning 2 / info 0" — the colour distinguishes them, but the SR user reads three pills in the same neutral voice. aria-label needs to spell it out: "5 alertes critiques, 2 alertes d avertissement, 0 alerte informative".

**Fix:**

```tsx
// apps/web/app/page.tsx — declare a labels map alongside TYPE_LABELS
const STATUS_LABELS: Record<Briefing["status"], string> = {
  pending: "en attente",
  context_assembled: "contexte prêt",
  claude_running: "Claude en cours",
  completed: "terminé",
  failed: "échoué",
};

// then in the JSX (line ~146):
- <span className={... b.status === "completed" ? ... : ...}>{b.status}</span>
+ <span
+   className={... b.status === "completed" ? ... : ...}
+   aria-label={`Statut : ${STATUS_LABELS[b.status]}`}
+ >
+   {STATUS_LABELS[b.status]}
+ </span>
```

```tsx
// apps/web/app/briefings/page.tsx:149-160 — apply the same map + use the
// shared TYPE_LABELS for briefing_type:
- <span className="font-mono text-sm text-neutral-200">{b.briefing_type}</span>
+ <span className="font-mono text-sm text-neutral-200">
+   {TYPE_LABELS[b.briefing_type]}
+ </span>
```

```tsx
// apps/web/app/alerts/page.tsx:86-97 — wrap each counter pill with an aria-label
- <span className="px-2 py-0.5 rounded bg-red-900/40 text-red-200 font-mono">
-   critical {counts.critical}
- </span>
+ <span
+   className="px-2 py-0.5 rounded bg-red-900/40 text-red-200 font-mono"
+   aria-label={`${counts.critical} alerte${counts.critical !== 1 ? "s" : ""} critique${counts.critical !== 1 ? "s" : ""}`}
+ >
+   <span aria-hidden="true">critical {counts.critical}</span>
+ </span>
```

(repeat for warning + info, with appropriate French nouns.)

---

