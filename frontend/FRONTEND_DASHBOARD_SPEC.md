# Frontend Dashboard Specification

## Project

**techbold AI Service Desk Autopilot**  
Frontend dashboard specification for the hackathon MVP.

This document covers only the React technician dashboard. Backend services, ERP integration, SSH execution, AI agent orchestration, VM reset handling, and persistence are owned by the backend team and are intentionally out of scope here.

## Frontend Scope

The frontend is a React single-page dashboard for a technician who needs to:

- View assigned ERP tickets.
- Open a ticket and inspect customer/system context.
- Review AI-generated analysis and proposed actions.
- Approve, edit, reject, retry, or abort every action before it affects a customer VM.
- Follow live progress and audit logs.
- Review a structured activity draft.
- Submit the final activity through backend-provided endpoints.

The dashboard must optimize for demo clarity, technician control, and safety visibility. It must not execute shell commands, connect over SSH, store secrets, or implement ERP writes directly.

## Non-Goals

- No backend implementation.
- No SSH runner implementation.
- No AI agent implementation.
- No direct ERP client implementation in the browser unless explicitly provided by backend as a safe proxy contract.
- No secret storage in browser local storage, session storage, screenshots, logs, or visible UI.
- No mobile-native app.
- No production-grade multi-tenant administration.
- No framework-specific routing, server rendering, server actions, API routes, middleware, or deployment assumptions.

## Frontend Technology Assumption

- React only.
- Any routing should be client-side and framework-neutral.
- The UI should be deployable as a normal React SPA.
- The frontend may consume REST endpoints, WebSocket/SSE event streams, or mocked JSON during development, depending on what the backend exposes.

## Frontend Architecture

The coded dashboard should stay modular and feature-oriented:

- `src/App.tsx` remains a small composition root.
- `src/features/auth` owns login, session state, and the auth guard.
- `src/features/dashboard` owns the overview, ticket queues, sidebar routing state, command menu state, and high-level dashboard orchestration.
- `src/features/tickets` owns the ticket detail workspace and its workflow tabs.
- `src/components/blocks.tsx` contains adapted Blocks-style sidebar, command menu, dialogs, tables, and stat primitives.
- `src/components/ui` contains small reusable local primitives such as page headers, status labels, definition tables, log tables, empty states, and toasts.
- `src/data`, `src/lib`, and `src/types.ts` contain mock data, pure helpers, and shared types.

Reusable components should be extracted when behavior or structure appears in more than one screen. Feature-specific components should stay inside their feature folder unless another feature actually needs them.

## Visual Style Guide

The dashboard follows the Vercel-inspired design system in `../DESIGN.md`.

Required visual direction:

- Use a near-white app canvas (`#fafafa`) with white cards and Vercel hairline borders (`#ebebeb`).
- Use Inter for all typography: display, body, labels, chips, controls, technical captions, and table headers.
- Keep typography lightweight, geometric, and restrained with regular weights by default and medium weight only for compact controls that need scanability.
- Use filled, borderless, small-radius buttons. Primary uses ink (`#171717`); info uses Link Blue (`#0070f3`); success/complete uses green (`#00a67d`); destructive uses Error (`#ee0000`); caution uses Warning (`#f5a623`).
- Avoid decorative gradients, heavy shadows, and colorful dashboard chrome. Gradients are reserved only for data/hero-scale accent moments.
- Use accent colors sparingly for operational emphasis only. Priority-only chips (`Critical`, `High`, `Medium`, `Low`) use white fill with a current-color border and text color. Status chips use semantic soft fills: red for critical/high/error, yellow for pending/awaiting, amber for warning/caution, green for done/connected/passed/success, blue for open/info, grey for idle/draft/not-run.
- Badges use two treatments: soft status chips with text only, and compact metric chips with pastel fill plus colored text.
- Form fields sit on white/canvas-soft surfaces with hairline borders.
- Cards should use tight 8px rounding, minimal shadow at most, and a single hairline border.

## Primary User

**Remote technician**

The technician is responsible for resolving assigned customer Linux incidents. They need a dashboard that makes the AI useful but never autonomous without approval. The UI should make it obvious what ticket is selected, what system is affected, what the AI wants to do, what has already happened, and what still needs confirmation.

## Core UX Principles

- Human approval is mandatory before every system action.
- The technician can stop the run at any time.
- The audit trail is always visible or one click away.
- Proposed commands must be reviewable before execution.
- Dangerous or broad actions must be clearly flagged.
- The activity draft must be based on logged events, not a vague after-the-fact summary.
- Errors must be recoverable and explained in technician-friendly language.

## Dashboard Information Architecture

### Global Layout

The dashboard uses a work-focused layout:

- **Left sidebar:** global command search at the top, overview route, ticket routes, and the technician profile/sign-out control at the bottom.
- **Main workspace:** selected ticket details and tabbed workflow.
- **In-page breadcrumbs:** only on detail screens where the technician needs a path back to the tickets root.
- **Contextual safety/approval content:** shown inside the selected ticket workflow rather than in a persistent global header.

The first screen after login or load should be the overview screen with key queue stats and high-priority tickets. The ticket queue remains one click away through the sidebar.

The overview stats layout should show the two graph cards at half width each, followed by three smaller non-chart stats. Do not include an Activity Status stat.

## Top-Level Dashboard Areas

### 1. Ticket Queue

Purpose: Let the technician quickly find and open assigned tickets.

Required ticket fields:

- Ticket ID.
- Title or short problem summary.
- Customer name.
- Priority.
- Status.
- Created date or updated date.
- Optional assignment/technician label if provided.

Required functionality:

- Default sorting by date, newest first.
- Sorting by priority.
- Sorting by customer.
- Tables must use fixed, explicit column widths so headers, body cells, and repeated table instances remain visually consistent.
- Filtering by status.
- Search by ticket ID, title, or customer.
- Visible loading, empty, error, and unauthorized states.
- Clear selected-ticket state when the currently selected ticket is no longer available.

Acceptance criteria:

- A technician can identify title, customer, priority, and status without opening a ticket.
- The list remains usable with at least 50 tickets.
- Sorting/filtering does not lose the selected ticket unexpectedly.

### 2. Ticket Workspace

Purpose: Provide a focused workflow for one selected ticket.

The workspace is organized into tabs. Tabs should remain visible while working on a ticket and should show small status indicators where useful, such as pending approvals, running analysis, validation passed, or draft incomplete.

Required workspace header:

- Ticket ID and title.
- Customer name.
- Priority/status.
- Current run state: not started, analyzing, awaiting approval, executing, validating, ready to submit, submitted, failed, or aborted.
- Primary action button appropriate to state.
- Global abort/stop control when analysis or execution is active.

## Required Tab Structure

### Tab 1: Overview

Purpose: Show the original customer report, ERP ticket metadata, brief run analytics, and the next useful action.

Content:

- Brief analytics only: pending approvals, run events, validation state, and connection state.
- Customer problem report.
- Ticket status, priority, timestamps, and customer.
- Any ERP-provided notes or context.
- Read-only display of assigned technician if available.
- Next action controls, with one clear primary action at a time.

Functionality:

- Refresh ticket details.
- Copy ticket ID.
- Show clear error state if ticket details cannot load.

Requirements:

- The customer report must be readable without horizontal scrolling.
- Long reports should preserve line breaks.
- Ticket metadata should be displayed as a direct definition table, not as a card-within-card.
- No backend credentials or SSH secrets are displayed here.

### Tab 2: System

Purpose: Show customer system context needed for technician decision-making.

Content:

- Host label or VM name.
- Operating system if provided.
- Connection target display, redacted as needed.
- Service/application hints if provided.
- Backend connection readiness state.
- Technician approval prompt before any connection is attempted.

Functionality:

- Request/load customer system information for the selected ticket.
- Show explicit "Approve connection" action when backend is ready.
- Show connection status: not requested, awaiting approval, connecting, connected, failed, disconnected.
- Show redacted credential labels only, never private key contents or tokens.

Requirements:

- The UI must separate "system info loaded" from "SSH connection approved".
- The technician must clearly approve connection before any backend SSH attempt.
- Connection failures must not block reading the ticket or audit log.

### Tab 3: Analysis

Purpose: Make the AI's reasoning reviewable before actions are proposed.

Content:

- Analysis status.
- Ranked hypotheses.
- Evidence per hypothesis.
- Confidence or priority indicator if available.
- Proposed diagnosis path.
- Safety notes or assumptions.

Functionality:

- Start analysis.
- Refresh/re-run analysis.
- Let the technician select or endorse a hypothesis if backend supports that flow.
- Show when analysis is using ticket-only context versus ticket plus system context.

Requirements:

- Analysis must distinguish symptom from suspected root cause.
- Proposed follow-up steps should be understandable to a technician.
- The UI should not imply that an action has executed when it is only proposed.

### Tab 4: Actions

Purpose: Provide the mandatory human approval gate for diagnostics and fixes.

Content:

- Queue of proposed actions.
- Action type: diagnostic, fix, validation, restart, file change, package/service operation, or other.
- Command preview or human-readable operation summary.
- Expected purpose.
- Risk level.
- Safety flags.
- Required approval state.
- Execution result once completed.

Functionality:

- Approve action.
- Edit action before approval, if backend supports command editing.
- Reject action with optional reason.
- Retry failed action.
- Abort current run.
- Mark action as manually handled by technician.
- Expand action details to view command/output summaries.

Requirements:

- Every command-affecting action must require explicit technician approval.
- The approve button must be disabled while action details are still loading.
- Potentially dangerous patterns must be visually flagged before approval.
- The UI must never auto-approve a queued action.
- Rejected actions must remain in the audit trail.

### Tab 5: Live Run

Purpose: Show current agent progress in a way the technician can follow during the demo.

Content:

- Timeline of current run events.
- Current active step.
- Pending approval indicator.
- Execution progress.
- Validation progress.
- Last backend heartbeat/event timestamp.

Functionality:

- Auto-scroll toggle.
- Pause visual auto-scroll without pausing backend execution.
- Jump to current event.
- Filter events by type: analysis, approval, command, output, validation, error.

Requirements:

- The technician can tell whether the system is thinking, waiting for approval, executing, validating, done, failed, or aborted.
- If the event stream disconnects, the UI must show a reconnecting or stale state.
- Command output should be summarized or collapsed by default when long.

### Tab 6: Audit Log

Purpose: Provide a complete chronological record of AI and technician actions.

Content:

- Timestamped events.
- Actor: AI, technician, backend, validator, ERP.
- Action name.
- Approval decision.
- Command summary.
- Redacted output summary.
- Safety warnings.
- Result status.

Functionality:

- Search audit entries.
- Filter by event type.
- Expand/collapse long entries.
- Copy a safe/redacted audit excerpt.
- Export/download audit log if backend provides this.

Requirements:

- The log should render as a table on the page background, not inside a card wrapper.
- Log filters/actions should sit above the log title. Do not add descriptive helper copy under the title.
- Every proposed, approved, rejected, retried, aborted, and executed action must be represented.
- Secrets must be redacted before display.
- The log must not allow hidden destructive actions to pass without visible trace.
- Audit log should remain available after run failure or abort.

### Tab 7: Validation

Purpose: Show proof that the customer benefit is restored.

Content:

- Validation checklist.
- Backend-provided validation commands or checks, summarized safely.
- Pass/fail status.
- Evidence text.
- Persistence check status if backend provides restart/reboot validation.

Functionality:

- Request validation after fix.
- Retry validation.
- Show failed checks with clear follow-up options.
- Link failed validation back to proposed follow-up actions.

Requirements:

- Validation result must be concrete, not just "looks fixed".
- The dashboard should distinguish "fix executed" from "fix validated".
- Submission should be blocked or warned when validation is missing.

### Tab 8: Activity Draft

Purpose: Review and submit the final ERP activity.

Required activity fields:

- `summary`
- `root_cause`
- `actions_taken`
- `commands_summary`
- `validation_result`

Content:

- Editable activity draft fields.
- Completeness checklist.
- Source references to audit log items where useful.
- Submit status.
- ERP response state.

Functionality:

- Generate or refresh draft from audit log.
- Allow technician edits before submission.
- Validate required fields are non-empty.
- Submit activity through backend endpoint.
- Show success state with activity ID if provided.
- Show retryable failure state.

Requirements:

- The UI must block submission until required fields are present.
- Commands summary must not include secret output.
- Root cause must be presented as technical cause, not just customer symptom.
- Technician must be able to edit the draft before submit.

## Suggested Workflow

1. Technician opens dashboard.
2. Ticket queue loads assigned open tickets.
3. Technician selects a ticket.
4. Ticket tab shows the customer report.
5. System tab loads customer system information.
6. Technician approves backend SSH connection.
7. Analysis tab starts or displays AI triage and detailed run analytics.
8. Actions tab receives proposed diagnostics/fixes.
9. Technician approves, edits, rejects, retries, or aborts each action.
10. Live Run and Audit Log tabs update continuously.
11. Validation tab confirms the fix.
12. Activity Draft tab generates the structured activity.
13. Technician reviews and submits the final activity.

## Run State Model

The frontend should represent these high-level states:

- `idle`: no ticket selected or no run started.
- `loading_ticket`: ticket detail is loading.
- `loading_system`: customer system info is loading.
- `awaiting_connection_approval`: backend is ready but needs technician approval.
- `analyzing`: AI analysis is running.
- `awaiting_action_approval`: one or more actions need technician confirmation.
- `executing`: an approved action is running.
- `validating`: backend validation is running.
- `ready_to_submit`: validation is complete and activity draft is ready.
- `submitting`: activity submission is in progress.
- `submitted`: ERP activity creation succeeded.
- `failed`: recoverable error occurred.
- `aborted`: technician stopped the run.

The UI may use more detailed internal states, but these states must be visible enough for the technician to understand what is happening.

## Backend-Facing Data Needs

The frontend needs backend-provided data or events for:

- Ticket list.
- Ticket detail.
- Customer system information.
- Connection approval request and status.
- AI analysis result.
- Proposed actions.
- Approval submission result.
- Live run events.
- Audit log entries.
- Validation result.
- Activity draft.
- Activity submission result.
- Error details safe for display.

The frontend does not define backend implementation details. These are UI contracts only.

## Error and Empty States

Required states:

- No tickets assigned.
- Ticket list failed to load.
- Ticket detail unavailable or 404.
- Unauthorized or expired session.
- Customer system info unavailable.
- Backend disconnected.
- Event stream disconnected.
- Action approval failed.
- Action execution failed.
- Validation failed.
- Activity draft generation failed.
- ERP activity submission failed.

Each error state should include:

- Clear short message.
- Safe technical detail if useful.
- Retry action when applicable.
- Recommended follow-up action, such as return to tickets, refresh, or abort run.

## Safety Requirements

The dashboard must make safety visible and enforceable at the UI level:

- Never auto-approve actions.
- Never display raw secrets.
- Clearly mark pending approvals.
- Clearly distinguish proposed actions from executed actions.
- Show rejected and aborted actions in the audit log.
- Provide a persistent abort control during active work.
- Flag risky commands or broad changes when backend marks them.
- Avoid storing sensitive event data in browser persistence.

Examples of high-risk actions that should be visually flagged when backend identifies them:

- Recursive permission or ownership changes.
- Deleting files or directories.
- Disabling firewall, audit, logging, or security controls.
- Restarting broad system services.
- Installing packages.
- Editing configuration files.
- Reading secret files or environment files.

## UI Requirements

- Work-focused dashboard layout.
- Dense but readable information hierarchy.
- No marketing or landing page.
- Ticket list should stay visible on desktop while working.
- On tablet/mobile widths, ticket list and approval queue can become drawers.
- Use clear status badges for priority, ticket status, run state, action risk, and validation result.
- Long command output should be collapsed by default.
- Required actions should be visually distinct from informational events.
- Primary action should always match current workflow state.

## Accessibility Requirements

- Keyboard-accessible tabs and controls.
- Visible focus states.
- Color must not be the only indicator of status.
- Buttons must have clear labels.
- Confirmation dialogs must identify the exact action being approved.
- Audit log and live run entries should be readable by screen readers in chronological order.

## Development Mocking Requirements

Because backend work is separate, frontend development should support mock data:

- Mock ticket list with multiple priorities/statuses.
- Mock selected ticket with customer report.
- Mock system info with redacted connection fields.
- Mock analysis with ranked hypotheses.
- Mock action approval queue.
- Mock live event stream.
- Mock audit log.
- Mock validation pass and validation fail states.
- Mock activity draft and submission success/failure.

Mocks must not include real secrets, private keys, bearer tokens, or real customer data.

## Demo Requirements

The frontend demo should make these moments obvious:

- Tickets load from the dashboard.
- Technician opens one ticket.
- Customer/system context is visible.
- Technician explicitly approves connection.
- AI analysis appears.
- Proposed diagnostics/fixes require approval.
- Every action appears in the live run and audit log.
- Validation result is visible.
- Activity draft contains required fields.
- Technician submits the activity.

## Definition of Done

The frontend dashboard is ready for backend integration when:

- All required tabs exist in the React UI design.
- Ticket queue supports sort, filter, search, loading, empty, and error states.
- Ticket workspace can display all required ticket/system/analysis/action/log/validation/activity data.
- Approval, reject, retry, and abort controls are represented.
- Activity draft validates required fields before submit.
- Mock data covers success and failure paths.
- No secrets are hardcoded or displayed.
- The UI remains usable at desktop and common laptop viewport sizes.
- Backend contract assumptions are documented and easy for backend engineers to map to real endpoints/events.
