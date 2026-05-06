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
| -------- | ----- |
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
-(<span className="font-mono text-sm text-neutral-200">{b.briefing_type}</span>) +
<span className="font-mono text-sm text-neutral-200">+ {TYPE_LABELS[b.briefing_type]}+ </span>;
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

### B3 — LiveEventsToast is invisible to screen readers + has no keyboard escape

**WCAG 2.2 SC 4.1.3 (Status Messages), SC 2.1.1 (Keyboard), SC 2.1.2 (No Keyboard Trap acceptable but no exit), SC 2.5.3 (Label in Name)**

apps/web/app/live-events-toast.tsx:135 renders the floating stack with no live region:

```tsx
{events.length > 0 && (
  <div className="fixed bottom-4 right-4 z-20 flex flex-col gap-2">
```

Consequences:

1. New events are not announced. SR users miss every "Nouveau briefing" / "Nouvelle alerte" — and the **whole point** of the toast is the live signal.
2. The connected badge (apps/web/app/live-events-toast.tsx:117-132) is rendered as a <span> decoration; the aria-label is set, but its content **changes** between "connecté" / "reconnecte…" and there is no aria-live so SR does not get the change.
3. The × close button has aria-label="Fermer la notification" (good) but the parent toast can be a <Link> (line 104). When focus is inside the link, pressing **Escape** does nothing — the user is forced to either Tab to ×, then Enter, or wait 8 s. WCAG 2.1.2 is not violated strictly (no hard trap), but per WAI-ARIA APG dismissible toasts MUST support Escape.

**Fix:**

```tsx
// apps/web/app/live-events-toast.tsx — wrap the stack and the connection badge
// in proper live regions; add Escape handler.

// 1. Connection badge — make the change announced politely
<span
  role="status"
- aria-label={connected ? "Live connecté" : "Live reconnecte…"}
+ aria-live="polite"
+ aria-atomic="true"
  ...
>
  <span aria-hidden="true" className={...} />
- live
+ <span className="sr-only">{connected ? "Live connecté" : "Live en reconnexion"}</span>
+ <span aria-hidden="true">live</span>
</span>

// 2. Toast stack — region wrapper
<div
  role="region"
  aria-label="Notifications temps réel"
  className="fixed bottom-4 right-4 z-20 flex flex-col gap-2"
>
  {events.map((e) => (
    <ToastChip key={e.localId} event={e} onDismiss={dismiss} />
  ))}
</div>

// 3. Inside ToastChip — make each chip a live region of its own
<Link href={href} className={cls} role={event.channel === "ichor:alerts:new" ? "alert" : "status"}>
  {Body}
</Link>

// 4. Add a global Escape handler in LiveEventsToast:
useEffect(() => {
  const onKey = (e) => {
    if (e.key === "Escape" && events.length > 0) {
      dismissAll();
    }
  };
  window.addEventListener("keydown", onKey);
  return () => window.removeEventListener("keydown", onKey);
}, [events.length, dismissAll]);
```

Note: avoid role="alert" for the briefing channel — it interrupts SR reading; status is the ARIA-equivalent of aria-live="polite".

Also add sr-only utility to Tailwind if not present (Tailwind v4 ships it by default).

---

### B4 — Asset cards: nested interactive elements + duplicated accessible name

**WCAG 2.2 SC 4.1.2 (Name, Role, Value), SC 2.4.4 (Link Purpose)**

Pattern used in apps/web/app/page.tsx:171-186, apps/web/app/assets/page.tsx:99-114:

```tsx
<Link key={asset.code} href={`/assets/${asset.code}`} prefetch={false}>
  <AssetCard ... />
</Link>
```

AssetCard (packages/ui/src/components/AssetCard.tsx:85-102) defends against this by switching from <button> to <article> when no onDrillDown is passed, BUT it still applies aria-label="EUR/USD: bias 0.30, 0 alerts" on the <article>. Two consequences:

1. The outer <a> has no accessible name of its own — Next.js Link just renders an <a> with the children inside. The SR user hears "EUR/USD: bias 0.30, 0 alerts" (from <article>'s aria-label) but the role announced is "lien" (link). The aria-label on a non-interactive element with no visible link text is a known SR-confusion pattern: NVDA reads the article label, then says nothing about the link destination.
2. Inside the article we also have an <h3> with the same asset code, so the SR user hears "EUR/USD" twice (once from the aria-label, once from the heading).
3. The English phrase "bias 0.30, 0 alerts" is announced inside French content (SC 3.1.2 if not flagged with lang="en").

**Fix:** give the link the proper accessible name and stop stamping aria-label on the article when the article is not the interactive root.

```tsx
// packages/ui/src/components/AssetCard.tsx:99-103
- <Wrapper
-   {...wrapperProps}
-   aria-label={`${formatAsset(asset)}: bias ${bias.toFixed(2)}, ${alertsCount} alerts`}
- >
+ <Wrapper
+   {...wrapperProps}
+   {...(interactive
+     ? { "aria-label": `${formatAsset(asset)} : biais ${bias.toFixed(2)}, ${alertsCount} alerte${alertsCount > 1 ? "s" : ""}` }
+     : {})}
+ >
```

```tsx
// apps/web/app/page.tsx:171-186 and apps/web/app/assets/page.tsx:99-114
- <Link key={asset.code} href={`/assets/${asset.code}`} prefetch={false}>
+ <Link
+   key={asset.code}
+   href={`/assets/${asset.code}`}
+   prefetch={false}
+   aria-label={`Détails ${asset.code.replace("_", "/")}`}
+ >
    <AssetCard ... />
  </Link>
```

Also: text inside the SR badge should be French. The chart aria-label="${title} sparkline, last value …" in ChartCard.tsx:102 is in English and the page is lang="fr". Translate the labels per locale (or add lang="en" on the wrappers, but cleaner to translate).

---

## HIGH — 8 findings

### H1 — No "skip to main content" link

**WCAG 2.2 SC 2.4.1 (Bypass Blocks)**

The layout has a sticky <header> with 4 nav items and a logo before {children}. Keyboard users have to Tab through 5+ links on every page load.

**Fix** — add at the very top of <body> in apps/web/app/layout.tsx:37:

```tsx
<body className="bg-neutral-950 text-neutral-100 antialiased min-h-screen flex flex-col">
+ <a
+   href="#main"
+   className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-50 focus:px-3 focus:py-2 focus:bg-neutral-100 focus:text-neutral-950 focus:rounded"
+ >
+   Aller au contenu principal
+ </a>
  <ServiceWorkerRegister />
  ...
- <div className="flex-1">{children}</div>
+ <div id="main" className="flex-1">{children}</div>
```

Note: every page <main> already exists at the top of children, so wrapping the children div with id="main" is the simplest patch.

---

### H2 — BiasBar / ConfidenceMeter ARIA labels are mathematically opaque

**WCAG 2.2 SC 1.1.1, SC 1.3.1**

packages/ui/src/components/BiasBar.tsx:53 — aria-label="Directional bias 0.42". A SR user has zero context to interpret 0.42. Same for ConfidenceMeter.tsx:48 — aria-label="Probability 38%" — no indication of what that probability is OF.

The 80 % credible interval is rendered visually as a translucent band but is **completely missing** from aria-label in both components. That is the entire point of the visualisation, gone for SR users.

**Fix:**

```tsx
// packages/ui/src/components/BiasBar.tsx:30-53
+ const describeBias = (b, ci) => {
+   const dir = b > 0.4 ? "long fort" : b > 0.1 ? "long faible" : b < -0.4 ? "short fort" : b < -0.1 ? "short faible" : "neutre";
+   const ciStr = ci
+     ? `, intervalle crédible 80 % de ${ci.low.toFixed(2)} à ${ci.high.toFixed(2)}`
+     : "";
+   return `Biais directionnel ${dir} (${b.toFixed(2)})${ciStr}`;
+ };

  return (
-   <div className={className} role="img" aria-label={ariaLabel ?? `Directional bias ${b.toFixed(2)}`}>
+   <div className={className} role="img" aria-label={ariaLabel ?? describeBias(b, credibleInterval)}>
```

```tsx
// packages/ui/src/components/ConfidenceMeter.tsx:43-49
  <svg ... role="img"
-   aria-label={label ?? `Probability ${(p * 100).toFixed(0)}%`}
+   aria-label={
+     `${label ?? "Probabilité"} : ${(p * 100).toFixed(0)} %` +
+     (credibleInterval
+       ? `, intervalle crédible 80 % de ${(credibleInterval.low * 100).toFixed(0)} % à ${(credibleInterval.high * 100).toFixed(0)} %`
+       : "")
+   }
  >
```

Same idea for RegimeIndicator.tsx:42-46 — current label is acceptable but it omits the **other two** state probabilities, which is half the information of the chart. Bring them in:

```tsx
aria-label={
  asset
-   ? `${asset} regime: ${STATE_LABELS[dominant]} (${(probs[dominant] * 100).toFixed(0)}%)`
+   ? `${asset} : régime dominant ${STATE_LABELS[dominant]} (${(probs[dominant] * 100).toFixed(0)} %), ` +
+     probs.map((p, i) => i !== dominant ? `${STATE_LABELS[i]} ${(p * 100).toFixed(0)} %` : null)
+       .filter(Boolean).join(", ")
    : `Régime : ${STATE_LABELS[dominant]}`
}
```

---

### H3 — ChartCard sparkline conveys trend by colour line only, no text alternative

**WCAG 2.2 SC 1.1.1**

packages/ui/src/components/ChartCard.tsx:97-105 exposes only aria-label="${title} sparkline, last value 0.61". The whole point of a sparkline is the **trend**, not the last value.

**Fix:** compute a trivial direction summary:

```tsx
const trendOf = (data) => {
  if (data.length < 2) return "données insuffisantes";
  const first = data[0];
  const last = data[data.length - 1];
  const min = Math.min(...data);
  const max = Math.max(...data);
  const slope = last - first;
  const dir = Math.abs(slope) < (max - min) * 0.05 ? "stable" : slope > 0 ? "haussier" : "baissier";
  return `${dir}, de ${first.toFixed(2)} à ${last.toFixed(2)}, plage ${min.toFixed(2)}–${max.toFixed(2)}`;
};

// then:
aria-label={`${title}, sparkline ${hasData ? trendOf(data) : "sans données"}`}
```

Add a <desc> child to the SVG for additional verbose detail (NVDA reads <desc> on hover when the user requests it).

---

### H4 — Touch / click targets below WCAG 2.2 24×24 minimum

**WCAG 2.2 SC 2.5.8 (Target Size — Minimum)** — 2.2 AA, no exemption applies (these are not inline-text targets).

- apps/web/app/live-events-toast.tsx:81-92 — close × button: only text-xs content (~12 px), no padding, no min-w/h. Effective target ~12×12 px.
- packages/ui/src/components/AlertChip.tsx:47-57 — acknowledge ✓ button: text-[10px], no padding beyond ml-1. Effective target ~10×10 px.
- packages/ui/src/components/TimelineMarker.tsx:80 — w-2.5 h-2.5 = 10×10 px when interactive.

**Fix** — bump to ≥ 24 × 24 px and grow the hit area without growing the visual:

```tsx
// live-events-toast.tsx:81
- <button ...
-   aria-label="Fermer la notification"
-   className="text-xs opacity-50 hover:opacity-100"
- >×</button>
+ <button ...
+   aria-label="Fermer la notification"
+   className="inline-flex items-center justify-center w-6 h-6 -m-1 text-base leading-none opacity-50 hover:opacity-100 focus-visible:opacity-100"
+ >
+   <span aria-hidden="true">×</span>
+ </button>
```

```tsx
// AlertChip.tsx:47
- <button type="button" onClick={...}
-   className="ml-1 text-[10px] opacity-60 hover:opacity-100"
-   aria-label="Acknowledge alert"
- >✓</button>
+ <button type="button" onClick={...}
+   className="ml-1 inline-flex items-center justify-center w-6 h-6 -my-1 -mr-1 rounded text-[10px] opacity-60 hover:opacity-100 focus-visible:opacity-100"
+   aria-label="Acquitter l'alerte"
+ >
+   <span aria-hidden="true">✓</span>
+ </button>
```

```tsx
// TimelineMarker.tsx — when interactive, expand the hit area via padding
// without growing the visible dot:
- "absolute top-0 -translate-x-1/2 w-2.5 h-2.5 rounded-full border " +
+ "absolute top-0 -translate-x-1/2 rounded-full border " +
  colorCls +
  (onClick
-   ? " cursor-pointer hover:scale-125 transition focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500"
-   : "")
+   ? " w-6 h-6 p-1.5 bg-clip-content cursor-pointer hover:scale-110 transition focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500"
+   : " w-2.5 h-2.5")
```

(The bg-clip-content + p-1.5 trick keeps the visible dot at ~12 px while making the hit area 24×24.)

---

### H5 — Form <input> pattern attribute fails accessible error reporting

**WCAG 2.2 SC 3.3.1 (Error Identification), SC 3.3.3 (Error Suggestion)**

apps/web/app/briefings/page.tsx:103-110 and apps/web/app/alerts/page.tsx:119-127:

```tsx
<input
  type="text"
  name="asset"
  placeholder="EUR_USD"
  pattern="[A-Z0-9_]{3,16}"
  ...
/>
```

When the pattern fails, browsers show a generic native tooltip ("Please match the requested format"). No description is given of what the format should be, nothing is announced to SR until the user blurs the field, and the error message is in the browser language (often en) inside our lang="fr" page.

**Fix:**

```tsx
<label className="flex flex-col text-xs text-neutral-400 gap-1">
  <span id="asset-label">Actif (code)</span>
  <input
    type="text"
    name="asset"
    defaultValue={params.asset ?? ""}
    placeholder="EUR_USD"
    pattern="[A-Z0-9_]{3,16}"
+   title="Code en majuscules, lettres / chiffres / souligné, 3 à 16 caractères. Exemple : EUR_USD"
+   aria-describedby="asset-help"
    className="..."
  />
+ <span id="asset-help" className="text-[10px] text-neutral-500">
+   Format : 3–16 caractères majuscules, ex. EUR_USD
+ </span>
</label>
```

title becomes the validation tooltip that browsers show; aria-describedby ensures the SR reads the helper text **before** the user types.

---

### H6 — <select> and <input> do not have an id/for association — only implicit wrap

**WCAG 2.2 SC 1.3.1 (Info and Relationships) + SC 4.1.2**

apps/web/app/briefings/page.tsx:87-100 (and many others) wrap the input in a <label> directly. This works in modern browsers, but:

- Some assistive techs (older NVDA + Firefox combo, some Dragon NaturallySpeaking versions) fail to associate implicit labels reliably.
- Voice-control software ("click Type") needs the label string to be reachable as the accessible name; implicit labels work but are fragile when the label text is in a child span.

**Fix:** use explicit htmlFor / id:

```tsx
- <label className="flex flex-col text-xs text-neutral-400 gap-1">
-   <span>Type</span>
-   <select name="type" ...>
+ <label htmlFor="briefing-type" className="flex flex-col text-xs text-neutral-400 gap-1">
+   <span>Type</span>
+   <select id="briefing-type" name="type" ...>
```

Apply consistently to all 5 form fields across briefings/page.tsx (1) and alerts/page.tsx (3).

---

### H7 — Audio player has no transcript and no captions

**WCAG 2.2 SC 1.2.1 (Audio-only and Video-only — Prerecorded), SC 1.2.2 (Captions Prerecorded)**

packages/ui/src/components/AudioPlayer.tsx:27-37 is a bare <audio controls> with the briefing TTS MP3. For pre-recorded audio-only content, **WCAG requires either a transcript OR an alternative for time-based media**. The briefing markdown is itself the transcript; we need to expose it explicitly.

**Fix** — accept the markdown alongside the audio URL and surface a "Lire la transcription" link:

```tsx
export interface AudioPlayerProps {
  src: string;
  label?: string;
  autoPlay?: boolean;
+ /** URL/anchor to the equivalent transcript (the briefing markdown body). */
+ transcriptHref?: string;
}

// in render:
+ {transcriptHref && (
+   <a href={transcriptHref} className="text-xs text-emerald-400 hover:text-emerald-300 underline-offset-2 hover:underline">
+     Lire la transcription écrite (équivalent texte)
+   </a>
+ )}
```

In apps/web/app/briefings/[id]/page.tsx, pass transcriptHref="#transcript" and add id="transcript" to the <article> containing the markdown. Document this guarantee in docs/decisions/ADR-009.

---

### H8 — aria-busy without an associated live region

**WCAG 2.2 SC 4.1.3 (Status Messages)**

packages/ui/src/components/DrillDownButton.tsx:86 sets aria-busy={loading || undefined} on the button. SR users will NOT be told the button is now busy unless the surrounding region is a live region or the spinner has its own announcement. The button accessible name **also does not change** to "Claude réfléchit…" because aria-label={ariaLabel ?? label} ignores loadingLabel.

**Fix:**

```tsx
// DrillDownButton.tsx:78-95
  return (
    <button
      type="button"
      onClick={isDisabled ? undefined : onClick}
      disabled={isDisabled}
      title={disabled && disabledReason ? disabledReason : undefined}
-     aria-label={ariaLabel ?? label}
+     aria-label={ariaLabel ?? (loading ? (loadingLabel ?? label) : label)}
      aria-busy={loading || undefined}
+     aria-live={loading ? "polite" : undefined}
      ...
    >
```

Better: hoist the live region to the parent. Add aria-live="polite" on the section that hosts the button.

---

## MEDIUM — 7 findings

### M1 — DisclaimerBanner uses <aside role="note"> but is the most legally important content

**WCAG 2.2 SC 1.3.1**

packages/ui/src/components/DisclaimerBanner.tsx:28-43 — <aside role="note"> is technically valid (W3C recently re-classified note as a structural role), but two issues:

1. The compact variant inserts an empty <strong> (line 38) — {compact ? "" : "Avis IA — EU AI Act Article 50"} — leaving an empty heading-ish element that some SRs announce as "vide".
2. Both variants use the same aria-label="Avis intelligence artificielle" while the **content** itself is the real disclosure. SR users hear "aside, Avis intelligence artificielle" then SR moves on without reading the body unless the user navigates into it. Better to drop aria-label and let the body content be the accessible name.

**Fix:**

```tsx
- <aside
-   role="note"
-   aria-label="Avis intelligence artificielle"
+ <aside
+   role="note"
+   aria-labelledby={compact ? undefined : "disclaimer-title"}
    className={...}
  >
-   <strong className={compact ? "" : "block mb-1 font-semibold"}>
-     {compact ? "" : "Avis IA — EU AI Act Article 50"}
-   </strong>
+   {!compact && (
+     <strong id="disclaimer-title" className="block mb-1 font-semibold">
+       Avis IA — EU AI Act Article 50
+     </strong>
+   )}
    {compact ? COMPACT_TEXT_FR : FULL_TEXT_FR}
  </aside>
```

Also: the banner is non-dismissible (good), but it has no tabindex of its own, so a SR user can only reach it through the document reading flow. That is fine for the body footer instance, but the **compact** instance lives at the top of <body> after the LiveEventsToast — confirm via DOM inspection it actually appears in reading order before <header>. Currently it does (layout.tsx:38-40). Good.

---

### M2 — Status badge claude_running uses animate-pulse with no reduce-motion override

**WCAG 2.2 SC 2.3.3 (Animation from Interactions, AAA, but EU best practice)** — partially mitigated.

packages/ui/src/components/BriefingHeader.tsx:31 and AlertChip.tsx:43-44 use animate-pulse for the "in progress" / critical states. The globals.css:60-69 block correctly disables CSS animations via prefers-reduced-motion, BUT Tailwind animate-pulse uses animation-duration: 2s set inline at the utility level — the global !important rule shortens it to 0.01ms. The pulse is therefore **not** disabled, only made imperceptibly fast (still cycles, just quickly). Acceptable per WCAG, but cleaner:

**Fix** — add an explicit override class for these pulse usages:

```css
/* globals.css */
@media (prefers-reduced-motion: reduce) {
  .animate-pulse {
    animation: none !important;
    opacity: 1 !important;
  }
}
```

---

### M3 — Markdown <a> links open in a new tab without warning the user

**WCAG 2.2 SC 3.2.5 (Change on Request, AAA, but BIT-required in France)**

apps/web/app/briefings/[id]/page.tsx:83-91 — every Markdown link is forced to target="\_blank" with no visual or programmatic indication. SR users hear "lien" but discover only after clicking that the page did not navigate.

**Fix:**

```tsx
a: ({ href, children }) => (
  <a
    href={href}
    target="_blank"
    rel="noopener noreferrer"
    className="text-emerald-400 hover:text-emerald-300 underline-offset-2 hover:underline"
+   aria-label={typeof children === "string" ? `${children} (nouvel onglet)` : undefined}
  >
    {children}
+   <span aria-hidden="true" className="ml-0.5 text-[0.8em]">↗</span>
  </a>
),
```

Same applies to BriefingHeader.tsx:84-91 (Écouter audio) and SourceBadge.tsx:46-56.

---

### M4 — RegimeIndicator coloured strip uses title for tooltip, no keyboard alternative

**WCAG 2.2 SC 1.4.13 (Content on Hover or Focus)**

packages/ui/src/components/RegimeIndicator.tsx:50-56:

```tsx
{probs.map((p, i) => (
  <div
    key={i}
    style={{ width: `${...}` }}
    title={`${STATE_LABELS[i]}: ${(p * 100).toFixed(0)}%`}
  />
))}
```

The title attribute is mouse-only (touch and keyboard cannot trigger it). The state labels are otherwise unreachable for keyboard / touch users.

**Fix:** render a small <dl> (visually hidden if you want) below the bar with the three state probabilities, OR put them in the aria-label of the wrapper as suggested in H2.

---

### M5 — Color-only indication of bias direction in BiasBar

**WCAG 2.2 SC 1.4.1 (Use of Color)**

The marker on the bar uses red for short, emerald for long, gray for neutral. There is no shape difference, no text, no pattern. For users with red-green deficiency (~ 6 % male population) a strong-short and strong-long are visually identical (both saturated bars).

**Fix** — add a small textual cue under or beside the bar:

```tsx
<div className={className} role="img" aria-label={...}>
  <svg ...>...</svg>
+ <div className="mt-1 text-[10px] font-mono text-neutral-500 flex justify-between">
+   <span>short</span>
+   <span>{b > 0 ? "▲" : b < 0 ? "▼" : "—"} {b.toFixed(2)}</span>
+   <span>long</span>
+ </div>
</div>
```

The arrow + numeric label provides redundant non-color encoding.

---

### M6 — Header logo <Link> accessible name competes with the visible "Ichor" text

**WCAG 2.2 SC 2.5.3 (Label in Name)**

apps/web/app/layout.tsx:47-70 — the link has aria-label="Ichor — accueil" AND visible text Ichor. Voice-control users saying "click Ichor" expect the link accessible name to **start with or contain** the visible text. "Ichor — accueil" does (starts with it), so this passes — but the visible text alone would be enough; current setup just risks the SR reading the visible "Ichor" then the aria-label "Ichor — accueil" depending on browser/SR pair.

**Fix:** drop the aria-label and let the visible text + the SVG aria-hidden="true" do the work:

```tsx
- <Link
-   href="/"
-   className="..."
-   aria-label="Ichor — accueil"
- >
+ <Link href="/" className="...">
    <svg ... aria-hidden="true">...</svg>
    <span className="text-base font-semibold tracking-tight">Ichor</span>
  </Link>
```

---

### M7 — Briefing markdown lists use list-inside which breaks long-line indent

**WCAG 2.2 SC 1.4.10 (Reflow) — partial**

apps/web/app/briefings/[id]/page.tsx:65-69:

```tsx
ul: ({ children }) => (
  <ul className="list-disc list-inside my-2 space-y-1">{children}</ul>
),
```

With list-inside, when an <li> wraps onto multiple lines, the second line returns to the left margin instead of aligning under the first character — making nested content harder to read at small viewports / 200 % zoom. Not a strict failure, but a known reflow pain point.

**Fix:** use list-outside + pl-5:

```tsx
ul: ({ children }) => (
  <ul className="list-disc list-outside pl-5 my-2 space-y-1">{children}</ul>
),
ol: ({ children }) => (
  <ol className="list-decimal list-outside pl-5 my-2 space-y-1">{children}</ol>
),
```

---

## LOW — 3 findings

### L1 — EmptyState uses role="status" but is not a status message

**WCAG 2.2 SC 4.1.3 (Status Messages)** — minor.

packages/ui/src/components/EmptyState.tsx:23-25 puts role="status" on the empty placeholder. role="status" implies aria-live="polite" — meaning every navigation between pages re-announces the empty state. Acceptable in some contexts, mildly annoying when a page loads with the empty state already present.

**Fix:** drop the role; the visual placeholder is enough.

```tsx
- <div role="status" className="...">
+ <div className="...">
```

---

### L2 — formatPct shows +0.00% for zero change

**WCAG 2.2 SC 1.3.1 — minor cognitive accessibility**

packages/ui/src/components/AssetCard.tsx:54 always prefixes + for non-negative values, including zero (+0.00%). For low-numeracy users / SR voicing, "plus zéro virgule zéro pourcent" is a small annoyance. Render 0.00% (no sign) when p === 0.

```tsx
const formatPct = (p) => -`${p >= 0 ? "+" : ""}${p.toFixed(2)}%`;
+`${p > 0 ? "+" : ""}${p.toFixed(2)}%`;
```

---

### L3 — <time dateTime> always uses ISO; visible text is human-friendly

This is correct behavior, just noting: SR users get the human-readable text (good) and crawlers / parsers get the ISO (good). No fix needed. Marked LOW just to note we verified it.

---

## No-issue zones (verified OK)

The following were inspected and either pass WCAG 2.2 AA cleanly or fall within reasonable best practice:

- **<html lang="fr">** declared in apps/web/app/layout.tsx:36 — SC 3.1.1 OK.
- **:focus-visible outline** with 2px solid var(--color-ichor-accent) and 2 px offset, applied globally in globals.css:72-76 — SC 2.4.7 OK; focus:outline-none is only used together with focus-visible:ring-2 replacements (AssetCard.tsx:92, DrillDownButton.tsx:89, TimelineMarker.tsx:83).
- **prefers-reduced-motion** honored globally in globals.css:60-69 — SC 2.3.3 OK (with the small caveat noted in M2).
- **No tabindex > 0** anywhere in the codebase (verified). SC 2.4.3 OK.
- **No outline: none without replacement** anywhere (verified).
- **Text contrast on body / nav / cards**: all body text colors (text-neutral-100 18.15:1, text-neutral-200 15.71:1, text-neutral-300 13.35:1, text-neutral-400 7.85:1, text-neutral-500 4.17:1) pass AA on #0a0a0b and on the layered bg-neutral-900/40 surfaces. SC 1.4.3 OK except for the text-neutral-600 BLOCKER B1.
- **DisclaimerBanner contrast**: amber-300/80 on amber-950/20 over neutral-950 measures **8.69:1** (compact) and **12.49:1** (full). Largely above the 4.5:1 threshold. SC 1.4.3 OK.
- **All status pills** (sky/amber/red/emerald -200 text on the matching -900/40 bg): 11.4 – 14.2:1. SC 1.4.3 OK.
- **.live connection indicator**: 10.29:1 connected, 4.17:1 reconnecting. AA-pass either state.
- **Status text colors inside ToastChip** (-100 shades on the matching -950/60 background): 14.5 – 15.5:1. AA-pass.
- **alt semantics on decorative SVGs**: every visible SVG icon (logo arrow layout.tsx:56, spinner DrillDownButton.tsx:46, chevron DrillDownButton.tsx:106) correctly carries aria-hidden="true". SC 1.1.1 OK.
- **<button type="button">** explicitly set on every dynamic button (AlertChip, DrillDownButton, EmptyState, the close ×, the form filter button) — no implicit type="submit" accidents. SC 4.1.2 OK.
- **HTML semantic landmarks**: every page provides <main>, briefings detail / briefings list / alerts / assets all use <header> + <section aria-labelledby="…"> + heading hierarchy h1 → h2 → h3 with no skipped levels. SC 1.3.1 OK.
- **AudioPlayer fallback content**: "Votre navigateur ne supporte pas l élément audio HTML5." renders for non-supporting agents. SC 1.2.1 partially OK (transcript still missing per H7).
- **Navigation aria-label="Navigation principale"** on <nav> — SC 2.4.6 OK.
- **<time dateTime>** used on every timestamp (briefings, alerts, briefing detail). SC 1.3.1 OK.
- **prefetch={false}** on the asset cards Link — irrelevant to a11y but confirms intent.

---

## Limits

The following were **NOT** part of this audit and need separate verification:

1. **Real screen-reader playback** with NVDA + Firefox, JAWS + Chrome, VoiceOver + Safari — none of the announced behaviour was actually heard, only inferred from source. Some browsers/SR pairs interpret role="status" and aria-live differently in edge cases.
2. **Zoom 400 %** on every viewport (SC 1.4.10 Reflow). The fixed-width SVGs (BiasBar 240 px, ConfidenceMeter 200 px, ChartCard 320 px default) are likely to overflow narrow viewports at high zoom — needs runtime test.
3. **Voice-control software** (Dragon NaturallySpeaking, Voice Access) — accessibility-name-vs-visible-label coverage was inferred but not driven.
4. **Color-blindness simulation** — palette inspection only; not run through Stark/Sim Daltonism.
5. **axe-core / Lighthouse a11y automated scan** — recommend running pnpm dlx @axe-core/cli http://localhost:3000 and lighthouse --only-categories=accessibility against every route after fixes.
6. **Focus order** in the rendered DOM — only the source order was verified; React portals or Tailwind position changes could re-order in practice.
7. **The not-found.tsx page** in scope was reviewed and looks clean (h1 + descriptive p + back link), no findings raised but the page was not otherwise stress-tested.
8. **ServiceWorkerRegister and /sw.js** — not user-facing UI, skipped.
9. **The BiasBar / ConfidenceMeter / RegimeIndicator under prefers-color-scheme: light** — the design is dark-only (colorScheme: "dark" in viewport metadata, layout.tsx:18), so light-mode contrast is moot. Documented choice.

---

## Recommended fix order (smallest → largest)

1. B1 (3 line changes) — kills the worst contrast failure immediately.
2. H1 (skip link, ~6 lines).
3. H4 (touch target sizes, ~3 components).
4. B2 (status labels, ~30 lines across 3 files).
5. H6, H5 (form a11y, ~10 lines).
6. H2, H3, M5 (chart ARIA labels, ~50 lines).
7. B3 (LiveEventsToast live region + Escape, ~25 lines).
8. B4 (AssetCard nested Link/Article fix, ~15 lines).
9. H7 (audio transcript, requires routing + ADR-009 amendment).
10. M1, M2, M3, M4, M6, M7, L1-3 (polish pass).

After the BLOCKER + HIGH set is shipped, re-run this audit AND a pnpm dlx @axe-core/cli automated scan against every route in the scope list.
