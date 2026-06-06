---
version: alpha
name: vercel-design-analysis
description: A Vercel-inspired operational dashboard language — stark ink on near-white canvas, hairline dividers, restrained neutral surfaces, and color used only for semantic badges, compact metric chips, action buttons, links, and occasional gradient-backed data accents.

colors:
  primary: "#171717"
  on-primary: "#ffffff"
  ink: "#171717"
  ink-hover: "#000000"
  body: "#4d4d4d"
  body-mid: "#a1a1a1"
  mute: "#888888"
  hairline: "#ebebeb"
  hairline-strong: "#a1a1a1"
  canvas: "#fafafa"
  canvas-soft: "#f5f5f5"
  canvas-card: "#ffffff"
  canvas-mid: "#f5f5f5"
  accent-cyan: "#50e3c2"
  accent-pink: "#ff0080"
  accent-violet: "#7928ca"
  link-blue: "#0070f3"
  link-deep: "#0761d1"
  link-bg-soft: "#d3e5ff"
  success: "#00a67d"
  success-soft: "#d8f7e6"
  success-deep: "#047857"
  error: "#ee0000"
  error-soft: "#f7d4d6"
  error-deep: "#c50000"
  warning: "#f5a623"
  warning-soft: "#ffefcf"
  warning-deep: "#ab570a"
  pending: "#f9cb28"
  pending-soft: "#fff7cc"
  pending-deep: "#8a6d00"
  develop-start: "#007cf0"
  develop-end: "#00dfd8"
  preview-start: "#7928ca"
  preview-end: "#ff0080"
  ship-start: "#ff4d4d"
  ship-end: "#f9cb28"
  severity-critical: "#ee0000"
  severity-high: "#ff4d4d"
  severity-medium: "#f9cb28"
  severity-low: "#00a67d"
  state-open: "#0070f3"
  state-neutral: "#888888"

typography:
  display-xl:
    fontFamily: Inter, system-ui, -apple-system, sans-serif
    fontSize: 96px
    fontWeight: 400
    lineHeight: 96px
    letterSpacing: -2.4px
  display-lg:
    fontFamily: Inter, system-ui, sans-serif
    fontSize: 72px
    fontWeight: 400
    lineHeight: 72px
    letterSpacing: -1.8px
  display-md:
    fontFamily: Inter, system-ui, sans-serif
    fontSize: 48px
    fontWeight: 400
    lineHeight: 48px
    letterSpacing: -1.2px
  display-sm:
    fontFamily: Inter, system-ui, sans-serif
    fontSize: 32px
    fontWeight: 400
    lineHeight: 36px
    letterSpacing: -0.6px
  display-xs:
    fontFamily: Inter, system-ui, sans-serif
    fontSize: 20px
    fontWeight: 400
    lineHeight: 28px
  body-lg:
    fontFamily: Inter, system-ui, sans-serif
    fontSize: 18px
    fontWeight: 400
    lineHeight: 28px
  body-md:
    fontFamily: Inter, system-ui, sans-serif
    fontSize: 16px
    fontWeight: 400
    lineHeight: 24px
  body-sm:
    fontFamily: Inter, system-ui, sans-serif
    fontSize: 14px
    fontWeight: 400
    lineHeight: 20px
  caption-mono:
    fontFamily: Inter, system-ui, sans-serif
    fontSize: 14px
    fontWeight: 400
    lineHeight: 20px
    letterSpacing: 1.4px
  caption-mono-sm:
    fontFamily: Inter, system-ui, sans-serif
    fontSize: 12px
    fontWeight: 400
    lineHeight: 16px
    letterSpacing: 1.2px
  button-md:
    fontFamily: Inter, system-ui, sans-serif
    fontSize: 14px
    fontWeight: 400
    lineHeight: 20px

rounded:
  none: 0px
  sm: 8px
  pill: 9999px
  full: 9999px

spacing:
  xxs: 2px
  xs: 4px
  sm: 8px
  md: 12px
  lg: 16px
  xl: 24px
  2xl: 32px
  3xl: 48px
  4xl: 64px

components:
  nav-bar:
    backgroundColor: "{colors.canvas}"
    textColor: "{colors.ink}"
    typography: "{typography.body-sm}"
    padding: "{spacing.md} {spacing.xl}"
  nav-link:
    textColor: "{colors.ink}"
    typography: "{typography.body-sm}"
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.on-primary}"
    borderColor: "{colors.primary}"
    typography: "{typography.button-md}"
    rounded: "{rounded.pill}"
    padding: "{spacing.xs} {spacing.md}"
  button-success:
    description: "Approve, submit, validate, and other positive committing actions."
    backgroundColor: "{colors.severity-low}"
    textColor: "{colors.canvas}"
    borderColor: "{colors.severity-low}"
    typography: "{typography.button-md}"
    rounded: "{rounded.pill}"
    padding: "{spacing.xs} {spacing.md}"
  button-danger:
    description: "Reject, abort, sign out, and destructive or negative actions."
    backgroundColor: "{colors.severity-critical}"
    textColor: "{colors.canvas}"
    borderColor: "{colors.severity-critical}"
    typography: "{typography.button-md}"
    rounded: "{rounded.pill}"
    padding: "{spacing.xs} {spacing.md}"
  button-warning:
    description: "Retry or cautionary actions."
    backgroundColor: "{colors.severity-medium}"
    textColor: "{colors.canvas}"
    borderColor: "{colors.severity-medium}"
    typography: "{typography.button-md}"
    rounded: "{rounded.pill}"
    padding: "{spacing.xs} {spacing.md}"
  button-info:
    description: "Load, start analysis, generate draft, and informational workflow actions."
    backgroundColor: "{colors.state-open}"
    textColor: "{colors.canvas}"
    borderColor: "{colors.state-open}"
    typography: "{typography.button-md}"
    rounded: "{rounded.pill}"
    padding: "{spacing.xs} {spacing.md}"
  button-outline-on-dark:
    backgroundColor: "{colors.canvas}"
    textColor: "{colors.ink}"
    borderColor: "{colors.hairline}"
    typography: "{typography.button-md}"
    rounded: "{rounded.pill}"
    padding: "{spacing.sm} {spacing.lg}"
  button-outline-sm:
    backgroundColor: "{colors.canvas}"
    textColor: "{colors.ink}"
    borderColor: "{colors.hairline}"
    typography: "{typography.button-md}"
    rounded: "{rounded.pill}"
    padding: "{spacing.xs} {spacing.md}"
  text-input:
    backgroundColor: "{colors.canvas}"
    textColor: "{colors.ink}"
    borderColor: "{colors.hairline}"
    typography: "{typography.body-md}"
    rounded: "{rounded.sm}"
    padding: "{spacing.md} {spacing.lg}"
    focusBackgroundColor: "{colors.canvas-card}"
    focusBorderColor: "{colors.primary}"
  status-chip:
    description: "Operational chips use semantic color, never decorative random hues."
    typography: "{typography.caption-mono-sm}"
    rounded: "{rounded.pill}"
    padding: "{spacing.xs} {spacing.md}"
    critical: "{colors.severity-critical}"
    high: "{colors.severity-high}"
    medium-pending: "{colors.severity-medium}"
    low-complete: "{colors.severity-low}"
    open: "{colors.state-open}"
    idle-neutral: "{colors.state-neutral}"
  card-content:
    backgroundColor: "{colors.canvas-card}"
    textColor: "{colors.ink}"
    borderColor: "{colors.hairline}"
    typography: "{typography.body-md}"
    rounded: "{rounded.sm}"
    padding: "{spacing.xl}"
  empty-state:
    description: "Empty states sit on the page background with a hairline/dashed border; avoid filled blue-black panels."
    backgroundColor: "transparent"
    textColor: "{colors.ink}"
    borderColor: "{colors.hairline}"
    rounded: "{rounded.sm}"
    padding: "{spacing.xl}"
  card-feature-product:
    backgroundColor: "{colors.canvas-card}"
    textColor: "{colors.ink}"
    borderColor: "{colors.hairline}"
    typography: "{typography.body-md}"
    rounded: "{rounded.sm}"
    padding: "{spacing.xl}"
  hero-band:
    backgroundColor: "{colors.canvas}"
    textColor: "{colors.ink}"
    typography: "{typography.display-xl}"
    padding: "{spacing.4xl} {spacing.xl}"
  content-band:
    backgroundColor: "{colors.canvas}"
    textColor: "{colors.ink}"
    typography: "{typography.display-md}"
    padding: "{spacing.4xl} {spacing.xl}"
  eyebrow-mono:
    textColor: "{colors.ink}"
    typography: "{typography.caption-mono}"
  divider-hairline:
    borderColor: "{colors.hairline}"
  footer:
    backgroundColor: "{colors.canvas}"
    textColor: "{colors.body}"
    typography: "{typography.body-sm}"
    padding: "{spacing.3xl} {spacing.xl}"

  # ─── Examples (illustrative) — auto-derived; resolve any TO_FILL markers below ───
  ex-pricing-tier:
    description: "Default Pricing tier card. Re-uses feature-card chrome with brand canvas-soft surface."
    backgroundColor: "{colors.canvas-soft}"
    textColor: "{colors.ink}"
    borderColor: "{colors.hairline}"
    rounded: "{rounded.sm}"
    padding: "{spacing.xl}"
  ex-pricing-tier-featured:
    description: "Featured/highlighted tier — polarity-flipped surface (dark fill + light text in light mode, light fill + dark text in dark mode)."
    backgroundColor: "{colors.ink}"
    textColor: "{colors.on-primary}"
    rounded: "{rounded.sm}"
    padding: "{spacing.xl}"
  ex-product-selector:
    description: "What's Included summary card — re-purposed for SaaS / B2B verticals (NOT a literal product gallery)."
    backgroundColor: "{colors.canvas-soft}"
    rounded: "{rounded.sm}"
    padding: "{spacing.xl}"
  ex-cart-drawer:
    description: "Subscription summary — re-purposed for SaaS / B2B (line items per add-on, not literal cart)."
    backgroundColor: "{colors.canvas}"
    rounded: "{rounded.sm}"
    padding: "{spacing.xl}"
    item-divider: "{colors.hairline}"
  ex-app-shell-row:
    description: "Sidebar nav row inside the App Shell example. Active state uses brand primary as the indicator."
    backgroundColor: "{colors.canvas}"
    activeIndicator: "{colors.primary}"
    rounded: "{rounded.sm}"
    padding: "{spacing.md} {spacing.lg}"
  ex-data-table-cell:
    description: "Default data-table th + td chrome. Header uses uppercase eyebrow typography; body uses body-sm."
    headerBackground: "{colors.canvas-soft}"
    headerTypography: "{typography.caption-mono}"
    bodyTypography: "{typography.body-sm}"
    cellPadding: "{spacing.md} {spacing.lg}"
    rowBorder: "{colors.hairline}"
    tableLayout: fixed
  ex-auth-form-card:
    description: "Sign-in / sign-up card. Re-uses feature-card chrome with text-input primitives inside."
    backgroundColor: "{colors.canvas-soft}"
    rounded: "{rounded.sm}"
    padding: "{spacing.xl}"
  ex-modal-card:
    description: "Modal dialog surface — same chrome as feature-card with elevated shadow."
    backgroundColor: "{colors.canvas}"
    rounded: "{rounded.sm}"
    padding: "{spacing.xl}"
  ex-empty-state-card:
    description: "Empty-state illustration frame."
    backgroundColor: "{colors.canvas-soft}"
    rounded: "{rounded.sm}"
    padding: "{spacing.3xl}"
    captionTypography: "{typography.body-md}"
  ex-toast:
    description: "Toast notification surface — feature-card shape + medium shadow."
    backgroundColor: "{colors.canvas}"
    rounded: "{rounded.sm}"
    padding: "{spacing.md} {spacing.lg}"
    typography: "{typography.body-sm}"

---


## Overview

The dashboard uses a Vercel-like restraint: ink-black text on a near-white `{colors.canvas}` (`#fafafa`) background, pure white cards, 1 px hairlines, and color only where it carries state. The surface should feel quiet and technical, not decorative.

Type stays Inter throughout. Headings and primary metric values use `{colors.ink}` (`#171717`). Supporting copy uses `{colors.body}` (`#4d4d4d`), while captions and placeholders use `{colors.mute}` (`#888888`).

Buttons are filled, borderless, small-radius rectangles. Badges use three compact treatments: priority chips with white fill plus current-color border/text, soft status chips with text only, and metric chips with pastel fill plus colored text. Avoid random hues, marker dots, and fully-outlined pills.

**Key Characteristics:**
- `{colors.canvas}` `#fafafa` page background, `{colors.canvas-card}` `#ffffff` card/dialog/table surface.
- `{colors.hairline}` `#ebebeb` dividers and card borders; no thick borders or stacked double borders.
- Ink text first; color appears only in badges, metric deltas, links, and primary/destructive/caution actions.
- Semantic colors: blue for links/open/info, green for low/done/connected/passed/success, red for critical/high/destructive/error, yellow for pending states, amber for warning/caution, grey for idle/neutral.
- Priority-only labels (`Critical`, `High`, `Medium`, `Low`) use white fill with a current-color border and text color; do not use the soft-fill badge treatment for priority labels.
- Gradient pairs exist only for data/hero-scale accent moments: Develop blue-to-teal, Preview violet-to-pink, Ship coral-to-amber.

## Colors

### Brand & Accent
- **Ink** (`{colors.ink}` — `#171717`): Headline text, body text on light surfaces, and primary CTA fill.
- **Cyan** (`{colors.accent-cyan}` — `#50e3c2`): Teal stop inside the Develop gradient.
- **Highlight Pink** (`{colors.accent-pink}` — `#ff0080`): High-saturation preview accent.
- **Violet** (`{colors.accent-violet}` — `#7928ca`): Deep preview accent.
- **Link Blue** (`{colors.link-blue}` — `#0070f3`): Links, open states, and informational actions.
- **Success Green** (`{colors.success}` — `#00a67d`): Low-priority, done, connected, passed, submitted, and success states.

### Surface
- **Canvas** (`{colors.canvas-card}` — `#ffffff`): Pure white card, dialog, modal, table surface.
- **Canvas Soft** (`{colors.canvas}` — `#fafafa`): Default page background.
- **Canvas Soft 2** (`{colors.canvas-soft}` — `#f5f5f5`): Inset regions, terminal surface, menus, secondary controls.
- **Hairline** (`{colors.hairline}` — `#ebebeb`): 1 px dividers, card borders, input borders.
- **Hairline Strong** (`{colors.hairline-strong}` — `#a1a1a1`): Deemphasised text and stronger neutral strokes.

### Text
- **Ink** (`{colors.ink}` — `#171717`): Every heading and primary value on light surfaces.
- **Body** (`{colors.body}` — `#4d4d4d`): Secondary text, subheadings, captions with normal importance.
- **Mute** (`{colors.mute}` — `#888888`): Lowest-priority text, placeholders, fine print.
- **On Primary** (`{colors.on-primary}` — `#ffffff`): Text on ink, blue, and red filled controls.

### Semantic
- **Info / Link** (`{colors.link-blue}` — `#0070f3`): Links, info buttons, and open chips.
- **Success** (`{colors.success}` — `#00a67d`): Done, connected, passed, submitted, low-priority, and positive-complete chips.
- **Link Deep** (`{colors.link-deep}` — `#0761d1`): Pressed/visited blue and blue chip text.
- **Link Bg Soft** (`{colors.link-bg-soft}` — `#d3e5ff`): Soft blue status and metric badges.
- **Error** (`{colors.error}` — `#ee0000`): Destructive actions and validation errors.
- **Error Soft** (`{colors.error-soft}` — `#f7d4d6`): Soft destructive/error badge backgrounds.
- **Warning** (`{colors.warning}` — `#f5a623`): Pending/caution indicators.
- **Pending Soft** (`{colors.pending-soft}` — `#fff7cc`): Soft yellow pending/awaiting badge backgrounds.
- **Warning Soft** (`{colors.warning-soft}` — `#ffefcf`): Stronger amber warning/caution backgrounds, especially for important terminal or workflow warnings.

## Typography

### Font Family
One face carries the system:
1. **Inter** — used for every display, body, button, link, form, label, chip, metric, and technical-caption role. Use weight 400 by default and 500 only where a compact control needs better scanability.

### Hierarchy

| Token | Size | Weight | Line Height | Letter Spacing | Use |
|---|---|---|---|---|---|
| `{typography.display-xl}` | 96px | 400 | 96px | -2.4px | Maximum hero scale. |
| `{typography.display-lg}` | 72px | 400 | 72px | -1.8px | Sub-hero displays. |
| `{typography.display-md}` | 48px | 400 | 48px | -1.2px | Section headlines. |
| `{typography.display-sm}` | 32px | 400 | 36px | -0.6px | Card-cluster headings. |
| `{typography.display-xs}` | 20px | 400 | 28px | 0 | Inline displays. |
| `{typography.body-lg}` | 18px | 400 | 28px | 0 | Lead paragraphs. |
| `{typography.body-md}` | 16px | 400 | 24px | 0 | Default body. |
| `{typography.body-sm}` | 14px | 400 | 20px | 0 | Secondary body. |
| `{typography.caption-mono}` | 14px | 400 | 20px | 1.4px | Uppercase section eyebrow using Inter. |
| `{typography.caption-mono-sm}` | 12px | 400 | 16px | 1.2px | Small uppercase labels using Inter. |
| `{typography.button-md}` | 14px | 400 | 20px | 0 | Button label. |

### Principles
- **Weight 400 for everything.** The brand never bolds. Negative tracking + size hierarchy do the emphasis work.
- **Tight negative tracking on display sizes.** Reverting to neutral tracking loses the precision feel.
- **Inter uppercase for eyebrows.** Use subtle positive tracking to make operational labels scan clearly without adding a second font.

### Implementation Font
Use Inter for the entire React dashboard. Do not load a separate display or monospace family.

## Layout

### Spacing System
- **Base unit**: 4 px.
- **Tokens**: `{spacing.xxs}` 2 px · `{spacing.xs}` 4 px · `{spacing.sm}` 8 px · `{spacing.md}` 12 px · `{spacing.lg}` 16 px · `{spacing.xl}` 24 px · `{spacing.2xl}` 32 px · `{spacing.3xl}` 48 px · `{spacing.4xl}` 64 px.
- **Section padding**: hero / content bands at `{spacing.4xl}` 64 px on desktop.
- **Card interior padding**: `{spacing.xl}` 24 px.

### Grid & Container
- Marketing content centres at ~1200 px.
- Product / announcement card grid: 2-up at desktop, 1-up at mobile.

### Responsive Strategy

#### Breakpoints

| Name | Width | Key Changes |
|---|---|---|
| Mobile | < 768px | Hero scales 96 → 48 px; grids 1-up; hamburger nav. |
| Desktop | ≥ 768px | Full hero + 2-up grids. |

#### Touch Targets
Buttons render ~32 – 40 px tall (8 vertical padding + 20 line). Mobile inflates touch area to meet WCAG 44 × 44 px.

#### Image Behavior
The brand uses sparse SVG illustrations for product moments (Grok, Voice, API). No photography on the marketing surface.

## Elevation & Depth

| Level | Treatment | Use |
|---|---|---|
| Level 0 — Flat | No shadow, no border. | Default. |
| Level 1 — Hairline | 1 px solid `{colors.hairline}` border. | Card chrome, button outlines (with translucent white). |

The brand uses no shadows. Hairline borders carry all elevation cues.

## Shapes

### Border Radius Scale

| Token | Value | Use |
|---|---|---|
| `{rounded.none}` | 0px | Full-bleed bands. |
| `{rounded.sm}` | 8px | Card chrome (the brand's `--radius` value). |
| `{rounded.pill}` | 9999px | Reserved for true circular affordances only; dashboard badges/buttons prefer small radii. |
| `{rounded.full}` | 9999px | Circular icon containers. |

## Components

### Buttons

**`button-primary`** — the filled ink action.
- Background `{colors.primary}` ink, text `{colors.on-primary}` white, no border, label `{typography.button-md}`, padding `{spacing.xs} {spacing.md}`, shape `{rounded.sm}` 8 px.

**`button-secondary`** — the neutral secondary action.
- Background `{colors.canvas-soft}` soft grey, text `{colors.ink}`, no border, same typography / padding scale / shape.

**`button-danger` / `button-warning` / `button-info`** — semantic filled actions.
- Danger uses `{colors.error}`, warning uses `{colors.warning}`, info uses `{colors.link-blue}`, success uses `{colors.success}`. Keep them borderless.

### Cards & Containers

**`card-content`** — the default content card.
- Background `{colors.canvas-card}` (`#ffffff`), text `{colors.ink}`, 1 px solid `{colors.hairline}` border, padding `{spacing.xl}`, shape `{rounded.sm}` 8 px.

**`card-feature-product`** — the product-feature card (Grok / Voice / API).
- Same chrome as `card-content`. Hosts an SVG illustration + headline + body + outline pill CTA.

### Inputs & Forms

**`text-input`** — the standard text input on dark.
- Background `{colors.canvas-soft}`, text `{colors.ink}`, 1 px solid `{colors.hairline}`, body in `{typography.body-md}`, padding `{spacing.md} {spacing.lg}`, shape `{rounded.sm}` 8 px.

### Navigation

**`nav-bar`** — the sticky top nav.
- Background `{colors.canvas}`, text `{colors.ink}`, padding `{spacing.md} {spacing.xl}`.

**`nav-link`** — link items inside nav.
- Text `{colors.ink}`, set in `{typography.body-sm}`.

**`footer`** — the footer band.
- Background `{colors.canvas}`, text `{colors.body}`, padding `{spacing.3xl} {spacing.xl}`. Body in `{typography.body-sm}`.

### Signature Components

**`hero-band`** — the dark hero with massive display headline.
- Background `{colors.canvas}`, text `{colors.ink}`, padding `{spacing.4xl} {spacing.xl}`. Headline in `{typography.display-xl}` (96 px weight 400 with `-2.4 px` tracking).

**`content-band`** — the standard content section.
- Background `{colors.canvas}`, text `{colors.ink}`, padding `{spacing.4xl} {spacing.xl}`. Section headline in `{typography.display-md}` preceded by a `{typography.caption-mono}` uppercase Inter eyebrow.

**`eyebrow-mono`** — the uppercase tracked Inter label above every section headline.
- Text `{colors.ink}`, set in `{typography.caption-mono}`. The brand's signature label style.

**`divider-hairline`** — the 1 px line between section bands.
- 1 px solid `{colors.hairline}`.

### Examples (illustrative)

> Auto-derived kit-mirror demonstration surfaces (`scripts/derive-examples-block.mjs`). Each `ex-*` entry references brand-native primitives so downstream consumers (`/preview-design`, `/generate-kit`) re-skin the same 10 surfaces consistently. `TO_FILL` markers indicate missing primitives — resolve in the LLM judgment pass.

**`ex-pricing-tier`** — Default Pricing tier card. Re-uses feature-card chrome with brand canvas-soft surface.
- Properties: `backgroundColor`, `textColor`, `borderColor`, `rounded`, `padding`

**`ex-pricing-tier-featured`** — Featured/highlighted tier — polarity-flipped surface (dark fill + light text in light mode, light fill + dark text in dark mode).
- Properties: `backgroundColor`, `textColor`, `rounded`, `padding`

**`ex-product-selector`** — What's Included summary card — re-purposed for SaaS / B2B verticals (NOT a literal product gallery).
- Properties: `backgroundColor`, `rounded`, `padding`

**`ex-cart-drawer`** — Subscription summary — re-purposed for SaaS / B2B (line items per add-on, not literal cart).
- Properties: `backgroundColor`, `rounded`, `padding`, `item-divider`

**`ex-app-shell-row`** — Sidebar nav row inside the App Shell example. Active state uses brand primary as the indicator.
- Properties: `backgroundColor`, `activeIndicator`, `rounded`, `padding`

**`ex-data-table-cell`** — Default data-table th + td chrome. Header uses uppercase eyebrow typography; body uses body-sm.
- Properties: `headerBackground`, `headerTypography`, `bodyTypography`, `cellPadding`, `rowBorder`

**`ex-auth-form-card`** — Sign-in / sign-up card. Re-uses feature-card chrome with text-input primitives inside.
- Properties: `backgroundColor`, `rounded`, `padding`

**`ex-modal-card`** — Modal dialog surface — same chrome as feature-card with elevated shadow.
- Properties: `backgroundColor`, `rounded`, `padding`

**`ex-empty-state-card`** — Empty-state illustration frame.
- Properties: `backgroundColor`, `rounded`, `padding`, `captionTypography`

**`ex-toast`** — Toast notification surface — feature-card shape + medium shadow.
- Properties: `backgroundColor`, `rounded`, `padding`, `typography`


## Do's and Don'ts

### Do
- Use `{colors.canvas}` (`#fafafa`) as the page surface and `{colors.canvas-card}` (`#ffffff`) for cards/dialogs/tables.
- Set hero headlines in `{typography.display-xl}` Inter weight 400 with restrained tracking. The precision is the voice.
- Use small-radius, filled controls for dashboard actions; reserve full circles for icons only.
- Use Inter everywhere, including sentence-case text, uppercase eyebrows, labels, chips, and metric counters.
- Use Vercel semantic soft fills for status chips and metric chips; avoid outlined badges.

### Don't
- Don't introduce dark-mode chrome or charcoal dashboard surfaces.
- Don't bold display headlines. Weight 400 is the entire scale.
- Don't use outlined pills for primary workflow actions. Use filled, borderless controls.
- Don't drop a drop-shadow on cards. Hairline borders carry elevation.
- Don't substitute Inter with a second display or mono family. A single restrained type voice is part of the dashboard system.
