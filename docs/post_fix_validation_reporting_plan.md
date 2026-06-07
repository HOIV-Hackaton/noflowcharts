# Post-Fix Validation And Reporting Plan

## Goal

Fix the terminal-agent flow so it cannot stop at a successful repair. After any approved fix, the system must collect validation evidence, require technician confirmation, automatically generate an activity draft, and then wait for explicit human submission to Phoenix.

## Decisions

- Automatically generate the activity draft after validation confirmation succeeds.
- Stop the terminal agent after successful validation evidence is collected; do not keep proposing more commands.
- Keep final activity submission explicitly human-triggered.
- Do not mark a ticket `DONE` until Phoenix activity submission succeeds.

## Current Failure Mode

- `TerminalManager` records terminal commands separately from the canonical `RunManager` command-result lifecycle.
- Terminal validation commands can succeed without setting `validation_status=evidence_collected` or `RunStatus.AWAITING_VALIDATION_CONFIRMATION`.
- `RunManager.confirm_validation` only checks `CommandResult` rows, so successful terminal validation evidence is ignored.
- The frontend has no strong handoff from successful terminal validation to activity generation.
- The frontend currently calls direct `PATCH DONE` after activity submission, even though the backend already sets `DONE` as part of `submit_activity` and rejects direct `DONE` status changes.

## Backend Plan

1. Make terminal completion reliable.

   Update `TerminalManager._capture_output` to search the accumulated pending command output for `__NOFLOW_EXIT:<id>:<code>__`, not only the latest PTY read chunk. This prevents lost completions when the marker is split across reads.

2. Promote terminal validation evidence into run state.

   After a terminal command completes successfully, detect whether it is validation evidence using the same rules as the rest of the backend: validation intent, `curl`, health checks, `systemctl is-active`, smoke tests, or successful output indicating the service is reachable/healthy.

3. Stop terminal-agent continuation after validation succeeds.

   When successful validation evidence is detected:

   - set `validation_status=evidence_collected`
   - set run status to `awaiting_validation_confirmation`
   - audit `validation_evidence_collected`
   - broadcast `validation_evidence_collected`
   - set `runtime.agent_active = False`
   - do not call `_safe_propose_agent` again

4. Allow validation confirmation from terminal evidence.

   Extend `RunManager.confirm_validation` so it accepts successful terminal validation commands in addition to `CommandResult` validation commands. Keep the existing guard that concrete validation evidence is required.

5. Automatically generate activity draft after validation confirmation.

   Add a backend endpoint or response flow that lets the frontend confirm validation and immediately generate the draft. The preferred minimal approach is frontend orchestration: call `confirmValidation`, then call `generateActivityDraft` after the confirmation succeeds.

6. Preserve explicit human submission.

   Do not auto-review or auto-submit the activity. The technician must review/edit and click submit. `RunManager.submit_activity` remains the only backend path that posts to Phoenix and then sets the ticket `DONE`.

## Frontend Plan

1. Handle terminal validation events.

   In `TechnicianConsole.handleRunWebSocketEvent`, respond to `validation_evidence_collected` by:

   - setting phase to `verification`
   - refreshing run state, audit events, terminal logs, and metrics
   - showing a notice that validation evidence is ready for confirmation
   - guiding the technician to confirm validation

2. Auto-generate draft after validation confirmation.

   Update `runValidation` so after `backendApi.confirmValidation(...)` succeeds, it calls `backendApi.generateActivityDraft(...)`, maps the draft into state, sets phase to `final_analysis`, and navigates to the activity tab.

3. Use concrete terminal evidence.

   Build validation confirmation text from the latest successful terminal validation command when available. Fall back to the current generic evidence only if backend state already contains non-terminal validation evidence.

4. Remove duplicate direct `DONE` patch.

   Remove the frontend call to `backendApi.setTicketStatus(ticketId, "DONE")` after activity submission. The backend already performs Phoenix activity creation and ticket completion atomically in `RunManager.submit_activity`.

5. Make the terminal handoff explicit.

   Display a clear message in the terminal when validation evidence has been collected: the agent stops, the technician must confirm validation, and the activity draft will be generated after confirmation.

## Tests

Backend tests:

- PTY exit marker split across reads still completes the terminal command.
- Successful terminal fix routes to a validation command.
- Successful terminal validation marks evidence collected and stops agent continuation.
- `confirm_validation` accepts successful terminal validation evidence.
- Activity draft generation works after terminal validation confirmation.

Frontend checks:

- `npm run build`
- Manual flow: accept fix, accept validation, confirm validation, verify draft auto-generates, review/edit, submit activity, confirm ticket becomes `DONE` only after submission.

## Safety Invariants

- Every SSH command still requires technician approval.
- Risky commands still require safety review and typed confirmation where configured.
- Activity generation can be automatic after validation confirmation, but final submission cannot be automatic.
- No secrets or raw secret-bearing output are exposed in frontend events, audit logs, or activity text.
- Ticket `DONE` status is only set after Phoenix activity submission succeeds.
