# SPEC v2 — Design system & frontend tokens

**Date** : 2026-05-04
**Compagnon de** : `D:\Ichor\SPEC.md` (Phase 2 Ichor)
**Source** : recherche READ-ONLY web 2026 (Stripe, Bloomberg, Vercel/Geist, Anthropic, IBM CVD-safe, Linear, Aladdin, OpenBB, TradingView)

## 1. Design tokens (tableaux exacts copiables Tailwind v4 `@theme`)

### 1.1 Palette (16 colors, dark-first, OKLCH-ready, CVD-safe)

Bull/bear bleu/orange (8 % d'hommes ont une déficience rouge-vert → IBM CVD-safe palette + David Nichols + Stripe accessible color systems).

| Token              | Hex                      | Usage                        |
| ------------------ | ------------------------ | ---------------------------- |
| `--bg-base`        | `#0A0D11`                | Fond app racine              |
| `--bg-surface`     | `#10141A`                | Cartes, panels               |
| `--bg-elevated`    | `#161B23`                | Modals, popovers             |
| `--bg-overlay`     | `rgba(8,10,14,0.72)`     | Scrim modal                  |
| `--border-subtle`  | `rgba(255,255,255,0.06)` | Séparateurs implicites       |
| `--border-default` | `rgba(255,255,255,0.10)` | Bordures cartes              |
| `--border-strong`  | `rgba(255,255,255,0.18)` | Focus, selected              |
| `--text-primary`   | `#E6EDF3`                | Body, titles                 |
| `--text-secondary` | `#A4ADBA`                | Labels (≥4.5:1)              |
| `--text-muted`     | `#6E7785`                | Disabled (3:1 large only)    |
| `--bull`           | `#3B9EFF`                | Hausse / positive (CVD-safe) |
| `--bear`           | `#FF8C42`                | Baisse / negative (CVD-safe) |
| `--warn`           | `#FFB000`                | Amber, alertes               |
| `--alert`          | `#DC267F`                | Magenta haute priorité (IBM) |
| `--accent-warm`    | `#C15F3C`                | Touche organique Anthropic   |
| `--accent-violet`  | `#785EF0`                | Régime / IA / scenarios      |

**Doubler ▲/▼ et signe +/− avec la couleur** (WCAG SC 1.4.1 — never color alone). Test grayscale obligatoire.

### 1.2 Typography scale (modular ratio 1.200, base 14px)

Famille : `Geist Sans` (UI), `Geist Mono` (data, prix, tickers tabular-nums), `Fraunces` ou `Source Serif 4` (briefing/learn éditorial — éviter Inter générique).

| Token          | Size / line / weight / tracking     | Usage                            |
| -------------- | ----------------------------------- | -------------------------------- |
| `text-xs`      | 11 / 16 / 500 / 0.02em              | Badges, ticker tags              |
| `text-sm`      | 12 / 18 / 500 / 0.01em              | Captions, table rows secondaires |
| `text-base`    | 14 / 20 / 400 / 0                   | Body default                     |
| `text-md`      | 16 / 24 / 400 / 0                   | Reading paragraph                |
| `text-lg`      | 18 / 26 / 500 / -0.01em             | Section titles                   |
| `text-xl`      | 22 / 30 / 600 / -0.02em             | Card titles                      |
| `text-2xl`     | 28 / 36 / 600 / -0.02em             | Page H2                          |
| `text-3xl`     | 36 / 44 / 700 / -0.03em             | Page H1                          |
| `text-display` | 48 / 56 / 700 / -0.04em             | Hero                             |
| `text-num-lg`  | 32 / 36 / 500 mono / 0 tabular-nums | Prix, KPI hero                   |

### 1.3 Spacing (12 steps, base 4px)

`space-0..space-24` : 0 / 1 / 4 / 8 / 12 / 16 / 20 / 24 / 32 / 40 / 48 / 64 / 96.

### 1.4 Radius

`radius-none` 0 / `radius-sm` 4 / `radius-md` 8 / `radius-lg` 12 / `radius-xl` 16 / `radius-full` 9999.

### 1.5 Shadow (dark-tuned, low-opacity)

| Token              | Valeur                           |
| ------------------ | -------------------------------- |
| `shadow-xs`        | `0 1px 2px rgba(0,0,0,0.40)`     |
| `shadow-sm`        | `0 2px 6px rgba(0,0,0,0.45)`     |
| `shadow-md`        | `0 6px 16px rgba(0,0,0,0.50)`    |
| `shadow-lg`        | `0 16px 32px rgba(0,0,0,0.55)`   |
| `shadow-glow-bull` | `0 0 24px rgba(59,158,255,0.25)` |

### 1.6 Motion scale (60 % workhorse / 30 % secondaire / 10 % expressif)

| Token           | Valeur                              | Usage                     |
| --------------- | ----------------------------------- | ------------------------- |
| `dur-instant`   | 80ms                                | Toggle, checkbox          |
| `dur-fast`      | 150ms                               | Hover, tooltip            |
| `dur-base`      | 220ms                               | Transitions standard      |
| `dur-slow`      | 320ms                               | Modal, drawer             |
| `dur-cinematic` | 500ms                               | Route transition, scrub   |
| `ease-respond`  | `cubic-bezier(0.2, 0, 0, 1)`        | Réponse input (workhorse) |
| `ease-enter`    | `cubic-bezier(0, 0, 0.2, 1)`        | Apparition                |
| `ease-exit`     | `cubic-bezier(0.4, 0, 1, 1)`        | Disparition               |
| `ease-spring`   | `cubic-bezier(0.34, 1.56, 0.64, 1)` | Modal pop, success        |
| `ease-snap`     | `cubic-bezier(0.12, 0, 0.08, 1)`    | Toggle, tab               |

### 1.7 Z-index scale (10 layers nommés)

| Token              | Valeur | Layer                 |
| ------------------ | ------ | --------------------- |
| `z-base`           | 0      | Content               |
| `z-sticky`         | 100    | Sticky table headers  |
| `z-dropdown`       | 200    | Selects, menus        |
| `z-overlay`        | 300    | Drawers latéraux      |
| `z-modal-backdrop` | 400    | Scrim                 |
| `z-modal`          | 410    | Modal content         |
| `z-popover`        | 500    | Tooltips, hover-cards |
| `z-toast`          | 600    | Notifications         |
| `z-command`        | 700    | Cmd+K palette         |
| `z-debug`          | 9999   | Dev overlay           |

## 2. Architecture information par page-type

- **Home dashboard** : grille 12-col, zones `hero régime` (top, h~280px) + `bias-strip` + `cards key sessions` + `briefing teaser` + `alerts feed`. Aladdin tabs persistants + Linear sidebar collapsible 64↔256px. Bloomberg-tape footer optionnel toggleable.
- **Drill-down asset** : hero asset (price, sparkline 30j, regime badge) + tabs `Overview / Chart / Sources / Scenarios / Notes`. Chart ~60 % viewport, panel droit pour bias/news.
- **Time-machine replay** : full-bleed canvas + slider scrub bottom (timeline 365j), keyboard arrows. Pause/play/speed + frame-by-frame. Pattern Heer & Robertson : stages séparés axis-rescale puis valeurs.
- **Knowledge-graph** : full-bleed `react-force-graph`, sidebar inspector droite 320px, breadcrumb haut, Cmd+K pour jump entité.
- **Scenarios** : split-view 2-col (compose gauche / preview droite) ou 3-col compare. Pattern OpenBB widgets liés par paramètres groupés.
- **Alerts list** : table dense TanStack avec virtualization, filtres latéraux, row-detail expand inline.
- **Briefing detail** : layout éditorial 1-col 720px max, marges aérées (Linear/Stripe), TOC sticky droite, Fraunces serif body.
- **Learn page** : layout cours-style, progression sticky, illustrations Anthropic-warm, glossary tooltip inline.
- **Settings** : pattern Stripe/Linear sections verticales, sidebar nav gauche, save bar sticky footer.

## 3. Comparatif inspirations (à emprunter / à éviter)

| Source              | À emprunter                                                                                               | À éviter                                                                               |
| ------------------- | --------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------- |
| Bloomberg           | Density data tables, keyboard-first, command palette, multi-panel customizable                            | Palette amber-on-black, keyboard ésotérique, aucune whitespace, courbe d'apprentissage |
| Aladdin             | Design system cohérent, tabs persistants avec carousel, color-coded risk heatmaps, accessibility built-in | Skin SAP-like daté, lourdeur enterprise, modals en cascade                             |
| OpenBB              | Widgets liés par paramètres groupés, AI agents inline, dashboards taggables/foldable                      | Esthétique générique encore peu différenciante                                         |
| Linear              | Vitesse perçue, sidebar étroite, Cmd+K, motion snap, typo dense aérée                                     | Pas de vrai pattern data-viz lourde                                                    |
| Stripe              | Color system perceptuel CIELAB, contrast pre-vérifié, restrained accent (blue=link only)                  | Risque feeling "flat" sur dense data                                                   |
| Vercel/Geist        | Geist Sans+Mono, letter-spacing -0.04em, near-zero radius marketing                                       | Trop minimal pour notre densité                                                        |
| TradingView         | Side-panel split editor, multi-chart 2x2, pattern detection auto                                          | Surcharge boutons, palette amateur                                                     |
| Anthropic claude.ai | Warm Crail #C15F3C éditorial, rounded humanist type, organic shapes briefing/learn                        | Pas adapté zones data-dense (réserver à briefing/learn/empty states)                   |

## 4. Composants finance — anatomie + states

### Composants existants à v2 (refondre)

- **BiasBar v2** : barre horizontale 8px, fill bull/bear, label %, tooltip détail. States : default / hover (height 12px, dur-fast) / loading (skeleton shimmer) / no-data.
- **AssetCard v2** : header (ticker mono, nom secondary), KPI prix `text-num-lg` tabular-nums, sparkline 30j 60×24px, regime chip, footer source. States : default / hover (border-strong) / focused / loading / error / stale (badge "données 5min+").
- **SessionCard v2** : titre session, range time, regime, top movers list, bias bar, conviction.
- **RegimeQuadrant v2** : 2×2 matrix (growth × inflation), pulse animant cellule active, hover reveal historique 90j. Reduced-motion : pulse → border-strong static.
- **ConfidenceMeter v2** : arc 0-100 %, colored par seuil (low<40 alert, mid amber, high bull), label numérique mono central.
- **ChartCard v2** : header titre + timeframe pills + actions (download, fullscreen, AI explain).
- **TimeMachineSlider v2** : track 365j, knob avec date label, ticks événements, keyboard left/right (1d), shift (7d), alt (30d).
- **AlertChip v2** : icon + label + dismiss, severity color, persistant ou auto-dismiss 6s.
- **SourceBadge v2** : favicon + nom + timestamp + reliability score 1-5 dots.
- **BriefingHeader v2** : titre Fraunces serif xl, dateline mono, regime badge, reading-time, TOC toggle.
- **Timeline v2** : vertical w/ events grouped par jour, virtualized.

### Nouveaux composants Phase 2

- **TradePlan v2** : entry / SL / TP@RR3 / cible RR15 trail / scheme partial 90/10 en colonnes mono, R:R calculé, AI critique button.
- **Walkthrough v2** : overlay coachmarks séquencé, progression 1/5, `prefers-reduced-motion` → fade only.
- **Glossary v2** : tooltip inline + drawer plein, recherche fuzzy, niveau débutant/avancé toggle.
- **ScenarioCompare v2** : 2-3 colonnes side-by-side avec diff visuel rouge/vert sur chiffres.
- **MetricTooltip v2** : hover-card avec formule, range historique 1Y, sparkline mini.
- **PostMortemCard v2** : trade clos avec result, leçons taggées, lien briefing du jour.
- **MultiTFContext v2** : 4 mini-cards alignées D1→M15 avec score d'alignement (cf. `SPEC_V2_TRADER.md` §2).
- **MobileBlocker v2** : page mobile-bloquée → écran "Best on desktop ≥1024px" + lien envoyer URL email.
- **AntiConfluenceFlag v2** : badge "régime contradictoire — no-trade" avec rationale détaillé.
- **EventCalendarFilter v2** : filtre red-only impacts × actifs trackés × fenêtre H-4h→H+1h sessions.

## 5. Micro-interactions 2026

| Interaction          | Pattern                                                     | Durée                       | Easing         |
| -------------------- | ----------------------------------------------------------- | --------------------------- | -------------- |
| Loading data table   | Skeleton rows shimmer + count placeholder                   | 220ms fade-in               | `ease-respond` |
| Loading chart        | Sparkline path stroke-dasharray draw                        | 500ms once                  | `ease-enter`   |
| Loading global       | Top progress bar (NProgress-style)                          | 320ms                       | `ease-respond` |
| Empty state          | Illustration warm + CTA primaire + tip secondaire           | 320ms scale 0.96→1          | `ease-spring`  |
| Error boundary       | Card border alert + retry + report + stack collapsed        | 220ms                       | `ease-enter`   |
| Optimistic update    | Apply mutation immédiate + revert on error toast            | instant + 150ms color flash | `ease-snap`    |
| Skeleton vs spinner  | Skeleton si layout connu, spinner si <300ms data            | —                           | —              |
| Pull-to-refresh      | Custom `overscroll-behavior-y: contain` + spinner threshold | 320ms release               | `ease-spring`  |
| Drag (panels)        | Lift shadow-md + scale 1.02 + cursor-grabbing               | 80ms                        | `ease-respond` |
| Scrub time-machine   | Live update chart + value count-up tabular-nums             | per-frame                   | linear         |
| Hover reveal tooltip | 200ms delay open, 80ms close                                | 150ms fade                  | `ease-out`     |
| Toast success        | Slide-in right + check icon + auto-dismiss 4s               | 320ms                       | `ease-spring`  |
| Modal open           | Backdrop 220ms + content scale 0.96→1                       | 320ms                       | `ease-spring`  |

## 6. Accessibilité data-rich finance

### 6.1 CVD-safe bull/bear

Bull `#3B9EFF` + ▲ + signe `+`, Bear `#FF8C42` + ▼ + signe `−`. Tester deuteranopie/protanopie/tritanopie via davidmathlogic.com/colorblind. Test grayscale obligatoire.

### 6.2 Contrast ratios cibles dark

- Body sur `#0A0D11` ≥ 4.5:1 (SC 1.4.3 AA). `#E6EDF3` ≈ 14:1, `#A4ADBA` ≈ 7:1 OK.
- Large text (≥18.66px ou 14pt bold) ≥ 3:1.
- UI components, icons, focus rings, sort indicators, cell borders zebra ≥ 3:1 (SC 1.4.11).
- Hover/focus/active states évalués indépendamment.

### 6.3 Focus + keyboard

- `:focus-visible` ring 2px `--bull` + offset 2px sur tout interactif.
- Tab order DOM = visual order. Skip-links "Aller au contenu / aux filtres / au graphique".
- Cmd+K palette globale, J/K navigation listes, ? cheatsheet.

### 6.4 Screen reader tables + heatmaps

- `<th scope="col|row">`, `<caption>` descriptive, `aria-sort` sur sortable.
- Heatmap : `role="img"` + `aria-label="EUR/USD régime risk-on confiance 78 %"` + table fallback caché visuellement, `aria-describedby` méthodologie.
- Chart : `<figure>` + `<figcaption>` + summary textuelle ("Hausse 3.2 % sur 30j, vol moyenne").

### 6.5 Reduced motion alternatives

`@media (prefers-reduced-motion: reduce)` désactive : régime pulse (border-strong), orbs ambient (opacity statique), sparkline draw (path final direct), scrub auto (manuel only), modal scale (fade only). Toujours offrir final-frame static + bouton "rejouer".

## 7. Animation principles par catégorie

| Catégorie  | Animation                  | Durée       | Easing                                            |
| ---------- | -------------------------- | ----------- | ------------------------------------------------- |
| Ambient    | Régime pulse               | 2400ms loop | `ease-in-out` (opacity 0.6→1, désactivable)       |
| Ambient    | Background orbs            | 12s loop    | linear (translate3d, GPU-only, pause si reduced)  |
| Ambient    | Ticker tape                | constant    | linear (translateX, pause on hover)               |
| Data       | Sparkline draw             | 500ms       | `ease-enter` (stroke-dasharray, once on mount)    |
| Data       | Chart timeframe transition | 320ms       | `ease-respond` (morph staged Heer & Robertson)    |
| Data       | Value count-up             | 320ms       | `ease-out` (rAF, tabular-nums)                    |
| Data       | Heatmap cell update        | 220ms       | `ease-snap` (background-color crossfade)          |
| Feedback   | Success                    | 320ms       | `ease-spring` (check icon scale 0→1)              |
| Feedback   | Error shake                | 320ms       | `ease-snap` (3 oscillations small amplitude)      |
| Feedback   | Loading shimmer            | 1600ms loop | linear (gradient mask sweep, GPU)                 |
| Navigation | Route transition           | 220ms       | `ease-respond` (fade + 8px slide-up)              |
| Navigation | Drawer slide               | 320ms       | `ease-spring` (translateX, backdrop fade 220ms)   |
| Navigation | Modal pop                  | 320ms       | `ease-spring` (scale 0.96→1 + fade)               |
| Navigation | Tab switch                 | 150ms       | `ease-snap` (underline slide + content crossfade) |

## 8. Mobile companion — gates + gestures

### 8.1 Pages full-mobile vs blocked

- **Full-mobile** : Home dashboard (cards stack vertical), Briefing detail, Alerts list, Learn, Settings, /today, /post-mortems.
- **Mobile-adapted réduit** : Asset drill-down (chart simplifié, tabs scrollables horizontal), /sessions/[asset], /scenarios/[asset].
- **Mobile-blocked** (avec `<MobileBlocker>` + lien envoyer URL email) : Knowledge-graph (interaction 2D complexe), Time-machine replay (scrub précis), Scenarios compare 3-col, Workspace customize, /knowledge-graph, /replay/[asset].

### 8.2 Gestures

- **Swipe horizontal** : naviguer entre assets dans drill-down, entre sessions dans home cards.
- **Pull-to-refresh** custom (`overscroll-behavior-y: contain`) : refresh data via API ciblée.
- **Long-press card** : actions rapides (épingler, alerte, partager).
- **Swipe-to-dismiss** : alerts, toasts.
- **Double-tap chart** : reset zoom.
- iOS PWA : back button visible toujours (pas de gesture back natif standalone). Hook Page Visibility API + `document.wasDiscarded` pour refresh stale data.

### 8.3 PWA

- Badge API count alerts non lues sur icône.
- Push API VAPID briefing matinal opt-in + alerts critiques.
- Touch targets ≥ 48×48px.
- 60fps obligatoire (transform/opacity only).

## 9. Anti-patterns à éviter

- Rouge/vert seuls pour bull/bear (8 % hommes CVD, fail SC 1.4.1).
- Inter/Roboto par défaut sur briefing/learn (cookbook Anthropic : "boring generic").
- Rebuild à chaque switch theme (Tailwind v4 permet runtime via `[data-theme]`).
- `@apply` massif pour composants (v4 recommande JS components + tv).
- Animations layout-triggering (width/height/top/left) — préférer transform/opacity.
- Skeleton qui flicker à l'unmount sans `AnimatePresence exit`.
- Spinner pour <300ms (préférer skeleton ou rien).
- Toast pour erreurs critiques (préférer error boundary inline avec retry).
- Modals empilés (Aladdin legacy pain point).
- Multi-stage animations agressives 4+ étapes (préférer staging simple).
- Tooltip sans delay ouverture (apparition trop nerveuse).
- Sparkline animée sans frame final statique pour reduced-motion.
- Mobile copy-paste desktop sur knowledge-graph / time-machine.
- Color-only sort indicator (fail SC 1.4.11).

## 10. Sources principales

- Stripe : [accessible color systems](https://stripe.com/blog/accessible-color-systems) / [Elements Appearance API](https://docs.stripe.com/elements/appearance-api)
- Bloomberg : [Terminal UX hide complexity](https://www.bloomberg.com/company/stories/how-bloomberg-terminal-ux-designers-conceal-complexity/) / [modern icon cutting-edge](https://www.bloomberg.com/company/stories/innovating-a-modern-icon-how-bloomberg-keeps-the-terminal-cutting-edge/)
- Tailwind v4 : [theme variables](https://tailwindcss.com/docs/theme), Mavik [tokens 2026](https://www.maviklabs.com/blog/design-tokens-tailwind-v4-2026/)
- IBM CVD-safe + David Nichols : [color-hex](https://www.color-hex.com/color-palette/1044488), [colorblind tester](https://davidmathlogic.com/colorblind/)
- WCAG 2.2 : [W3C](https://www.w3.org/TR/WCAG22/) + [WebAIM](https://webaim.org/articles/contrast/)
- Motion : [baraa easing curves](https://www.baraa.app/blog/easing-curves-are-a-design-language) / [motion.dev easing](https://motion.dev/docs/easing-functions) / [Heer&Robertson 2007](https://idl.cs.washington.edu/files/2007-AnimatedTransitions-InfoVis.pdf)
- Vercel/Geist : [typography](https://vercel.com/geist/typography) / [SeedFlip breakdown](https://seedflip.co/blog/vercel-design-system)
- Anthropic : [frontend aesthetics cookbook](https://platform.claude.com/cookbook/coding-prompting-for-frontend-aesthetics) / [Claude Design news](https://www.anthropic.com/news/claude-design-anthropic-labs)
- BlackRock : [Design Systems Must Grow Evolve](https://medium.com/blackrock-engineering/design-systems-must-grow-and-evolve-b3b8994b1977)
- OpenBB : [Workspace Dashboards](https://docs.openbb.co/workspace/analysts/dashboards)
- Maxime Heckel : [Framer Motion advanced](https://blog.maximeheckel.com/posts/advanced-animation-patterns-with-framer-motion/)
- firt.dev : [PWA tips](https://firt.dev/pwa-design-tips/)
