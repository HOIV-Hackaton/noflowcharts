# AI Agent Backend Implementation Plan

## Repository Reality

Backend is only `backend/app/main.py` with `/health`. No ERP client, SSH runner, agent, safety layer, audit log, activity generator, database layer, tests, or backend API routes exist yet. Frontend is a plain Vite placeholder. The OpenAPI spec in `docs/phoenix-openapi.yaml` is the authoritative ERP contract.

## Agreed Architecture Decisions

- Optimize for a working demo MVP first.
- Persist important run state, actions, command results, activity drafts, and audit events in SQLite.
- Use SQLModel for database models/access.
- Do not support safe continuation of interrupted active runs after backend restart; persisted data is for visibility and audit.
- Keep route organization by resource.
- Expose REST APIs plus WebSocket progress streaming.
- Use typed JSON WebSocket events with replay support after reconnect.
- Use Azure OpenAI as the first real LLM provider behind a provider abstraction.
- If no LLM credentials are configured, disable agent features with a clear error instead of falling back to heuristics.
- Require explicit technician confirmation before the first SSH connection to a customer VM.
- Require explicit technician confirmation for every AI-proposed SSH/system action, including diagnostics, fixes, validation commands, retries, and edited commands.
- Treat common diagnostics and config/log reads as low-risk/read-only, but still present them for confirmation before execution.
- Classify commands as `read_only`, `mutating`, `risky_mutating`, or `blocked`.
- Allow `sudo` only as flagged/risky behavior requiring typed confirmation and safety checks.
- Block hard-fail commands before SSH execution.
- When safety blocks a command, show the reason, allow technician edit, and ask the agent for a safer alternative.
- Set Phoenix ticket status to `PENDING` when a run starts and `DONE` only after activity submission succeeds.
- Generate activity as an LLM draft, require all scoring fields, and require explicit human review before submission.
- Require validation command evidence plus human confirmation before final activity submission; where safe and proportionate, validation should show persistence after a relevant service restart or reboot-equivalent check.
- Keep audit events append-only.
- Truncate stored/shown stdout and stderr to about 32 KB per stream.
- Always redact command output before sending it to the LLM.
- Target frontend UX: ticket detail page owns run state, command approvals, logs, validation, and activity review.
- Ticket overview must show title, customer, priority, and status, with sorting/filtering by at least date, priority, and customer/status where feasible. Phoenix supports `date`, `priority`, and `status`; customer sorting may need backend/client-side sorting after fetch.
- Add a `REPORT.md` later as the recommended technical write-up for submission.

## Backend Module Plan

Create this modular backend structure under `backend/app/`:

- `core/config.py`
  - Load Phoenix, SSH, SQLite, and Azure OpenAI settings.
  - Required Phoenix settings: `PHOENIX_API_BASE_URL`, `PHOENIX_API_TOKEN`.
  - Required SSH settings when executing commands: `SSH_PRIVATE_KEY_PATH`; `SSH_USERNAME` is fallback only.
  - Azure OpenAI settings should be isolated here, e.g. endpoint, API key, deployment/model, API version.
  - Keep `/health` dependency-free; missing `.env` should fail only when protected operations are called.
  - Never expose ERP token, Azure key, SSH key path contents, or secrets in frontend responses/logs.

- `core/errors.py`
  - Shared exception types for ERP, SSH, safety, agent, database, validation, and activity submission errors.
  - Convert upstream 401/404/422/timeouts into clean FastAPI responses.
  - Ensure secret values are redacted from exception messages.

- `core/redaction.py`
  - Central redaction utility for logs, LLM prompts, command outputs, audit payloads, and activity drafts.
  - Redact configured secrets and obvious credential patterns: bearer tokens, API keys, passwords, private key material, `.pem` contents, env secret values.

- `db/session.py`
  - Create SQLite engine and SQLModel session factory.
  - Own database initialization.
  - Keep DB file path configurable, with a sensible backend-local default.

- `db/models.py`
  - Normalized SQLModel tables for persisted state.
  - `Run`: run ID, ticket ID, status, timestamps, selected customer system snapshot, current action ID, validation status, human confirmation flags.
  - `Action`: proposed command/action state, command classification, intent, risk reason, expected signal, typed confirmation status, edited command if any.
  - `CommandResult`: action ID, command, exit code, truncated stdout/stderr, timeout flag, started/ended timestamps.
  - `AuditEvent`: append-only event ID, run ID, type, timestamp, payload JSON, redaction status.
  - `ActivityDraft`: run ID, summary, root cause, actions taken, commands summary, validation result, description, review status.
  - `WebSocketEvent`: monotonic event ID, run ID, type, timestamp, payload JSON for reconnect replay.

- `repositories/runs.py`
  - Repository wrapper over SQLModel for runs, actions, command results, activity drafts, and audit events.
  - Enforce append-only audit writes.
  - Provide replay queries for WebSocket reconnect by `last_event_id`.

- `schemas/phoenix.py`
  - Pydantic models matching `docs/phoenix-openapi.yaml`: `Employee`, `Ticket`, `CustomerSystem`, `Customer`, `ActivityCreate`, `Activity`, `TicketStatus`.
  - Use `int` for 64-bit IDs.
  - Include optional fields exactly as spec: `sla_due_at`, `created_at`, `notes`, optional activity text fields.

- `schemas/runs.py`
  - Internal/frontend-facing models for run state, action state, command classification, approval requests, typed confirmations, command results, audit events, WebSocket events, and generated activity draft.
  - Model state explicitly: `created`, `pending`, `diagnosing`, `awaiting_approval`, `running_command`, `awaiting_validation_confirmation`, `ready_for_activity`, `submitted`, `aborted`, `failed`.

- `clients/phoenix.py`
  - HTTP client for Phoenix ERP using bearer auth.
  - Implement `get_me()`, `list_tickets(status=None, priority=None, sort="date")`, `get_ticket(ticket_id)`, `get_customer_system(ticket_id)`, `get_customer(customer_id)`, `set_ticket_status(ticket_id, status)`, `create_activity(activity)`, `reset_me()`.
  - Add timeouts and limited retries for transient failures.
  - Never expose token in errors.
  - Keep `reset_me()` available through an explicit dev/admin path only; it clears activities and reboots VMs, so it should not be part of the normal ticket flow.

- `services/ssh_runner.py`
  - Runtime implementation connects over real SSH to the VM from Phoenix `CustomerSystem.system`.
  - Use Phoenix `system.username` first; fallback to `.env` `SSH_USERNAME` only if Phoenix omits username.
  - Run exactly one technician-confirmed command per call.
  - Enforce connect timeout, command timeout, 32 KB stdout/stderr truncation per stream, exit code capture, and timeout reporting.
  - Return structured output, not raw unbounded logs.

- `services/safety.py`
  - Pre-execution command validation and classification.
  - Classify as `read_only`, `mutating`, `risky_mutating`, or `blocked`.
  - Mark common diagnostics and config/log reads as `read_only` low-risk actions, but do not auto-execute them.
  - Require explicit technician confirmation for `read_only` and `mutating` commands.
  - Require typed confirmation for `risky_mutating` commands, including `sudo`.
  - Block hard-fail patterns from scoring: database deletion/reinitialization, broad `rm -rf`, `chmod -R 777`, deleting `/etc`, `/home`, `/var/lib/postgresql`, logs/history, disabling firewall/security/audit, running app/db as superuser to bypass perms, and secret-reading commands where possible.
  - Re-check every edited command before execution.

- `services/audit_log.py`
  - Append every key action and command to SQLite `AuditEvent` records.
  - Events: ticket loaded, customer system loaded, SSH connection confirmed, ticket set pending, plan generated, command classified, command proposed, approved/rejected/edited command, typed confirmation, safety result, blocked command, command result, validation evidence, human validation confirmation, activity draft generated, activity reviewed, activity submitted, ticket set done, reset requested, abort.
  - Redact secrets from payloads and command output before storage.
  - Provide read APIs for frontend-visible logs.

- `services/activity_generator.py`
  - Generate complete `ActivityCreate` drafts from run history using the LLM provider.
  - Must fill scoring-required fields even though OpenAPI only requires `ticket_id`, `start_datetime`, `end_datetime`: `summary`, `root_cause`, `actions_taken`, `commands_summary`, `validation_result`.
  - Also include `description` because OpenAPI response marks it required on `Activity`.
  - Optimize content quality for scoring: root cause must be the technical cause, not the symptom; validation must state concrete customer benefit restored; commands summary must avoid secrets.
  - Block submission unless all scoring fields are non-empty and explicit human review is recorded.

- `agent/planner.py`
  - Own the troubleshooting loop logic.
  - Given ticket, customer system, safety policy summary, and recent observations, propose exactly one next command plus optional notes.
  - Output structure: intent, command, expected signal, risk level, command class hint, rollback note if applicable.
  - Do not execute SSH directly.
  - Do not receive raw unredacted command output.

- `agent/providers.py`
  - Define a provider abstraction for planner and activity generation.
  - Implement Azure OpenAI first.
  - Fail clearly when Azure OpenAI credentials are missing.
  - Keep provider boundary narrow enough to add other providers later.

- `services/run_manager.py`
  - Orchestrate one troubleshooting run with SQLite persistence.
  - On run start: load ticket/customer system via ERP, store snapshots, require explicit technician confirmation before SSH connection, set Phoenix ticket to `PENDING`, emit events.
  - For each step: call planner, classify command, then wait for technician confirmation before execution; risky commands require typed confirmation.
  - Use FastAPI background tasks for command execution so REST requests do not block on SSH.
  - Persist action state transitions and command results.
  - Support reject, edit, retry, abort, safer alternative request, validation command, human validation confirmation, activity draft, activity review, activity submit, and final status `DONE`.

- `api/routes_tickets.py`
  - Backend API for frontend ticket workflow: `GET /api/tickets`, `GET /api/tickets/{ticket_id}`, `GET /api/tickets/{ticket_id}/customer-system`, optional `GET /api/me`.
  - Proxy Phoenix data and normalize errors.
  - Support date/priority/status sorting via Phoenix where possible and customer sorting/filtering in backend if needed.

- `api/routes_runs.py`
  - Human-in-the-loop agent API: `POST /api/runs`, `GET /api/runs/{run_id}`, `POST /api/runs/{run_id}/confirm-ssh`, `POST /api/runs/{run_id}/next`, `POST /api/runs/{run_id}/approve`, `POST /api/runs/{run_id}/confirm-risk`, `POST /api/runs/{run_id}/reject`, `POST /api/runs/{run_id}/edit`, `POST /api/runs/{run_id}/retry`, `POST /api/runs/{run_id}/abort`, `POST /api/runs/{run_id}/validation/confirm`, `GET /api/runs/{run_id}/audit`.

- `api/routes_activity.py`
  - Activity review/submission: `POST /api/runs/{run_id}/activity/draft`, `PATCH /api/runs/{run_id}/activity/draft`, `POST /api/runs/{run_id}/activity/review`, `POST /api/runs/{run_id}/activity/submit`, `PATCH /api/tickets/{ticket_id}/status`.

- `api/routes_ws.py`
  - WebSocket endpoint for typed JSON run events.
  - Support reconnect replay by accepting `run_id` and `last_event_id`.
  - Event shape: `event_id`, `type`, `run_id`, `timestamp`, `payload`.
  - Frontend can recover with REST run state if replay is incomplete.

- `main.py`
  - Keep `/health`.
  - Register resource routers and WebSocket route.
  - Keep CORS for local frontend.
  - Initialize SQLite tables on startup.
  - Do not require Phoenix, SSH, or Azure credentials just to import app or serve `/health`.

- `tests/`
  - Add lightweight core tests during MVP, then broaden after the workflow is working.
  - Cover Phoenix client with mocked HTTP responses, safety classification/blocking rules, redaction, activity submission guards, run manager confirmation-before-SSH and approval-before-every-command behavior, WebSocket event replay, and SSH runner behavior through mocks.
  - Normal tests must not require live Phoenix VMs; real SSH is used by the running app, while tests replace the SSH transport with fakes/mocks.

## Build Order

1. Add backend dependencies: `httpx`, `paramiko`, `sqlmodel`, Azure/OpenAI SDK or HTTP client support, `pytest`, and HTTP mocking tools.
2. Implement `core/config.py`, `core/errors.py`, `core/redaction.py`, Phoenix schemas, and run schemas.
3. Implement SQLite setup, SQLModel tables, repositories, and database initialization.
4. Implement `clients/phoenix.py` and ticket routes so ERP workflow A works early.
5. Implement WebSocket event persistence/replay primitives before long-running agent work.
6. Implement `audit_log.py` and `safety.py` before any SSH execution.
7. Implement `ssh_runner.py` for real Phoenix-provided SSH targets, with tests that mock the SSH transport.
8. Implement Azure OpenAI provider and planner output parsing for one-command proposals.
9. Implement `run_manager.py` with strict state transitions, background command execution, mandatory SSH connection confirmation, mandatory per-command approval, and typed confirmations for risky commands.
10. Implement validation evidence plus human validation confirmation, including persistence-oriented checks after relevant service restarts when safe.
11. Implement LLM activity draft generation, human review guard, Phoenix activity submission, and final ticket status `DONE`.
12. Update README with setup, run, environment, architecture, assumptions, and troubleshooting; add `REPORT.md` after implementation details are known.
13. Add core tests during the MVP path, then broaden tests after the full workflow is usable.
14. Only after backend APIs stabilize, wire the frontend ticket detail flow to REST plus WebSocket events.

## Gotchas / Constraints

- Every Phoenix endpoint requires `Authorization: Bearer <PHOENIX_API_TOKEN>`.
- IDs are 64-bit integers; do not type them as strings unless only for display.
- OpenAPI says `ActivityCreate` only requires timestamps and ticket ID, but scoring requires complete documentation fields.
- OpenAPI includes `description` on activities; README's example omits it. Include it anyway.
- The SSH private key is never returned by ERP and must never reach the browser.
- `docker-compose.yml` mounts `./keys` read-only at `/keys`; `.env.example` already points there.
- Compose allows backend to start without `.env`, so config validation should fail only when protected operations are called, not at import time.
- Human approval must be enforced server-side for every SSH/system action, not only in the frontend.
- Typed risk confirmation must be enforced server-side for risky commands.
- Read-only classification lowers risk and improves UX, but does not remove the confirmation requirement.
- Edited commands must be reclassified and rechecked.
- Safety hard-fails are severe enough to zero incidents; block them before SSH.
- Audit logs must be append-only and redacted.
- Command output must be bounded to about 32 KB per stdout/stderr stream.
- Raw command output must be redacted before LLM prompts.
- Hidden incidents are fresh and unknown, so the agent should generalize from ticket symptoms and observations, not hardcode known fixes.
- Incidents are expected to be local Ubuntu service problems solvable over shell; keep the approach general and avoid incident-specific hardcoding.
- Minimal changes matter: prefer diagnosis, targeted edits/restarts, validation, and no broad installs or blanket permission changes.
- Unnecessary commands, restarts, and broad changes hurt tie-breakers even when the primary fix works.
