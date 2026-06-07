# Product

## Register

product

## Users

Remote support technicians working active customer incidents from the Phoenix ERP queue. They are operating under time pressure, often against unfamiliar Ubuntu systems, and need enough system context, agent reasoning, command evidence, and activity documentation to resolve the incident without losing human control.

## Product Purpose

This product is an AI-assisted service desk workspace for the techbold START Hack track. It loads assigned tickets from Phoenix ERP, retrieves the affected customer system, guides diagnosis and minimal SSH fixes behind technician approval gates, validates the customer benefit, and submits complete activity documentation back to Phoenix. Success means incidents are fixed on fresh hidden systems, every risky step remains reviewable, and the resulting activity captures the technical root cause, actions, command classes, and concrete validation proof.

## Brand Personality

Precise, controlled, operational. The interface should feel like a professional technician console: calm under pressure, explicit about system state, and strict about what is approved before anything touches a customer machine.

## Anti-references

Avoid toy chatbot patterns that hide the workflow behind a conversational feed. Avoid autonomous-agent styling that implies the AI can act without review. Avoid marketing-dashboard polish that buries tickets, commands, validation, or audit evidence behind decorative metrics. Avoid terminal-heavy interfaces that expose raw secret-bearing output or make the technician hunt for the next safe action.

## Design Principles

1. Keep the human in charge: every connection, command, retry, abort, validation, and activity submission must have visible state and a clear review path.
2. Diagnosis before fix: show hypotheses, system facts, and command evidence before encouraging changes to the customer VM.
3. Audit is part of the workflow: logs and actions should be readable while work is happening, not reconstructed after the incident.
4. Documentation should be hard to submit incomplete: root cause, actions taken, commands summary, and validation proof need clear review before Phoenix submission.
5. Optimize for the demo path without weakening safety: the fastest path should still preserve approval, bounded changes, and secret-safe output.

## Accessibility & Inclusion

Target WCAG AA for text contrast, keyboard navigation, focus visibility, and form controls. The product should not rely on color alone for priority, status, validation, or danger. Motion should respect reduced-motion preferences. Dense operational screens should remain usable at laptop widths typical for live judging and technician work.
