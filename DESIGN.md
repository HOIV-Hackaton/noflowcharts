---
version: alpha
name: techbold-dark-ops-console
description: A dark operational technician console for high-control service desk work. It uses a near-black workspace, zinc neutral panels, Geist typography, compact shadcn controls, and semantic color only for risk, status, validation, and destructive actions.

colors:
  background: "#09090b"
  foreground: "#fafafa"
  card: "#111113"
  card-foreground: "#f4f4f5"
  popover: "#111113"
  popover-foreground: "#f4f4f5"
  primary: "#fafafa"
  primary-foreground: "#09090b"
  secondary: "#27272a"
  secondary-foreground: "#f4f4f5"
  muted: "#18181b"
  muted-foreground: "#a1a1aa"
  accent: "#27272a"
  accent-foreground: "#fafafa"
  destructive: "#f87171"
  border: "#27272a"
  input: "#3f3f46"
  ring: "#a1a1aa"
  sidebar: "#0c0c0f"
  sidebar-foreground: "#f4f4f5"
  sidebar-accent: "#27272a"
  sidebar-border: "#27272a"

typography:
  family-sans: "Geist Variable, Inter, system-ui, -apple-system, sans-serif"
  family-heading: "Geist Variable, Inter, system-ui, -apple-system, sans-serif"
  family-mono: "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, Liberation Mono, monospace"
  page-title:
    fontSize: 24px
    fontWeight: 500
    lineHeight: 32px
    letterSpacing: 0
  section-title:
    fontSize: 18px
    fontWeight: 500
    lineHeight: 28px
    letterSpacing: 0
  card-title:
    fontSize: 16px
    fontWeight: 500
    lineHeight: 22px
    letterSpacing: 0
  body:
    fontSize: 14px
    fontWeight: 400
    lineHeight: 20px
    letterSpacing: 0
  caption:
    fontSize: 12px
    fontWeight: 500
    lineHeight: 16px
    letterSpacing: 0
  terminal:
    fontSize: 13px
    fontWeight: 400
    lineHeight: 20px
    letterSpacing: 0

rounded:
  md: 8px
  lg: 10px
  xl: 12px
  pill: 9999px

spacing:
  xs: 4px
  sm: 8px
  md: 12px
  lg: 16px
  xl: 24px
  2xl: 32px

components:
  app-shell:
    backgroundColor: "{colors.background}"
    textColor: "{colors.foreground}"
    maxWidth: 88rem
  sidebar:
    backgroundColor: "{colors.sidebar}"
    textColor: "{colors.sidebar-foreground}"
    borderColor: "{colors.sidebar-border}"
  card:
    backgroundColor: "{colors.card}"
    textColor: "{colors.card-foreground}"
    borderColor: "ring foreground / 10%"
    rounded: "{rounded.xl}"
    padding: "{spacing.lg}"
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.primary-foreground}"
    rounded: "{rounded.lg}"
    height: 32px
  button-outline:
    backgroundColor: "transparent or input / 30%"
    textColor: "{colors.foreground}"
    borderColor: "{colors.border}"
    rounded: "{rounded.lg}"
  button-destructive:
    backgroundColor: "destructive / 10%"
    textColor: "{colors.destructive}"
    rounded: "{rounded.lg}"
  input:
    backgroundColor: "input / 30%"
    textColor: "{colors.foreground}"
    borderColor: "{colors.input}"
    focusRing: "{colors.ring}"
    rounded: "{rounded.lg}"
  status-chip:
    rounded: "{rounded.pill}"
    fontSize: 12px
    semanticOnly: true
  terminal:
    backgroundColor: "{colors.background}"
    textColor: "{colors.foreground}"
    borderColor: "input / 70%"
    fontFamily: "{typography.family-mono}"
---

## Overview

The product is a dark operations workspace for remote technicians resolving real Linux incidents. The dark theme is intentional: technicians use it during focused incident response, often while reading terminal output and audit logs. The UI should feel controlled, explicit, and calm, not decorative.

Design serves the workflow. Tickets, system context, approval state, command review, logs, validation, and Phoenix activity submission are the important surfaces. Decorative metrics, marketing panels, or vague AI-agent language should never compete with the next safe action.

## Product Principles

- Human control is visible. Every connection, command, retry, abort, validation, and activity submission exposes its current state and review affordance.
- Diagnosis precedes mutation. Read-only context and evidence come before fix commands.
- Audit is not a separate afterthought. Logs and command summaries are part of the main work surface.
- Safety language is concrete. Use nouns like "backend SSH connection", "read-only diagnostics", "customer VM", and "Phoenix activity".
- One primary action per phase. Secondary actions can remain available, but the interface always identifies the next safe step.

## Color

The palette is restrained and state-rich. Neutral surfaces carry the app. Color is reserved for semantic meaning:

- `primary` is the high-contrast filled action color.
- `destructive` is only for abort, reject, reset, blocked commands, and errors.
- `secondary`, `muted`, and `accent` create neutral layers for cards, sidebars, tabs, inputs, and inactive controls.
- Status chips must pair text with labels, never color alone.
- Avoid decorative gradients, tinted glow, or broad saturated panels.

Contrast targets:

- Body text on background and cards must meet WCAG AA.
- Muted text must remain readable on card and page backgrounds.
- Destructive text must be legible on dark and tinted destructive surfaces.

## Typography

Use Geist Variable for headings, labels, body copy, controls, and values. Use the monospace stack only for commands, terminal output, and transcript excerpts.

Product UI uses compact fixed sizes. Do not use fluid display typography in the app shell. Page titles are 24px, section titles are 18px, card titles are 16px, and normal body/control text is 14px.

Labels and buttons use sentence case. Avoid uppercase labels except for short technical tags where the component already establishes that pattern.

## Layout

The app shell uses a sidebar, top header, and constrained content width. Spacing follows the Tailwind scale already used in the codebase:

- `gap-2` and `gap-3` for compact controls.
- `gap-4` and `gap-5` for panel rhythm.
- `p-3` and `p-4` for dense cards.
- `p-6` only for page-level breathing room.

Cards are functional containers for repeated data, review panels, dialogs, terminal surfaces, and activity forms. Do not nest cards inside cards. For workflow guidance, prefer a single panel with rows or a step rail rather than many repeated metric cards.

## Components

Buttons:

- Primary buttons are for the next safe workflow action.
- Outline buttons are for secondary navigation and non-committing actions.
- Destructive buttons are for abort, reject, disconnect, and reset only.
- Button labels must say what happens: "Approve command", "Reject", "Reset assigned VMs", "Submit activity".

Command review:

- Always show intent, risk class, command text, expected signal, and review controls before approval.
- Editable commands stay in a visible input or textarea, not hidden inside terminal-only text.
- Terminal hotkeys can remain as an expert path, but structured buttons must exist for demo clarity and accessibility.

Activity review:

- The activity cannot be submitted just because fields contain text.
- The UI must show all required Phoenix fields and validation readiness.
- Missing requirements should be visible inline before submission.

Reset:

- Environment reset is a high-impact development action.
- It must be gated by a confirmation dialog that states it clears generated activities and requests VM reboot.
- Typed confirmation is required.

Terminal:

- The terminal surface is full-width within the actions tab and uses the monospace stack.
- Safety notes appear above or near the terminal controls.
- Commands that can hang or open pagers should be described as blocked or converted by backend policy.

## Motion

Motion is minimal and state-based. Use existing shadcn/Radix transitions for dialogs, sheets, dropdowns, tabs, and toasts. Avoid page-load choreography. Respect reduced motion through existing component primitives and avoid adding custom animation without a reduced-motion fallback.

## Accessibility

- Preserve keyboard access for navigation, tables, dialogs, forms, tabs, terminal controls, and command review.
- Focus rings must remain visible.
- Do not rely on color alone for priority, risk, validation, or command status.
- Dialogs must have titles, descriptions, cancel actions, and safe disabled states.
- Long command strings and customer names must wrap without horizontal page overflow.
