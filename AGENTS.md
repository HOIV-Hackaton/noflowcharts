# AGENTS.md

## Scope

This file is for coding agents working on this repository.

It is not a prompt for the runtime AI technician agent inside the product.

## Core Rule

Do not assume context.

If anything is unclear, stop and ask the user before coding.

## Source Of Truth

Read these before meaningful implementation work:

- `README.md`
- `docs/case_study.md`
- `docs/scoring.md`
- `docs/phoenix-openapi.yaml`

Treat these docs as requirements. Do not invent API behavior, credentials, incidents, scoring rules, or product behavior.

## Project Map

- `backend/` contains the FastAPI backend.
- `frontend/` contains the React + Vite + TypeScript technician UI.
- `docs/` contains the case brief, scoring rubric, and Phoenix ERP API contract.
- `keys/` is for SSH private keys and must remain secret-bearing and local-only.
- `.env` is local-only. `.env.example` documents required variables without secrets.

## Required Architecture

Keep these responsibilities separate:

- ERP client
- SSH runner
- safety layer
- agent orchestration
- audit log
- activity generator
- frontend technician workspace

Do not collapse unrelated responsibilities into one large module.

Do not move secrets or privileged operations into the frontend.

## Coding Standards

Prefer small, direct changes over broad rewrites.

Keep code readable, typed where practical, and explicit about data boundaries.

Use clear names that reflect the domain in the case docs.

Avoid clever abstractions unless they remove real duplication.

Avoid speculative generalization.

Do not add compatibility layers unless there is a concrete need.

Do not hardcode hidden incidents, VM-specific fixes, credentials, tokens, paths, or customer data.

Keep functions focused. Split modules by responsibility, not by arbitrary layers.

Handle errors with clear messages and predictable failure modes.

Use timeouts for external calls where relevant: Phoenix API, SSH, and LLM/provider calls.

Keep retries bounded and intentional.

Do not swallow exceptions silently.

Do not leave dead code, unused files, debug prints, TODOs without owner/context, or placeholder implementations that look complete.

## Dependency Rules

Ask the user before adding any dependency.

If a dependency is approved, use the smallest suitable dependency and explain why it is needed.

Do not introduce a new framework or architecture pattern without approval.

## Safety Requirements To Preserve

The product must keep a human in control.

Do not code paths that allow unapproved SSH commands.

Do not implement dangerous blanket operations.

Do not create code that deletes customer data, clears logs/history, disables security controls without need, or exposes secrets.

Preserve complete audit logging for every command and key action.

Preserve review, approve, retry, and abort flows.

Prefer diagnosis before fix.

Prefer minimal, targeted system changes over broad filesystem or service changes.

Validation must prove the customer benefit is restored and the fix persists where relevant.

## Secrets And Data

Never commit `.env`, SSH keys, Phoenix tokens, LLM provider keys, customer secrets, or generated logs containing secrets.

Keep Phoenix API tokens and SSH private keys backend-only.

Never expose secrets through frontend code, API responses, logs, screenshots, activity text, test fixtures, or README examples.

Use `.env.example` for variable names only.

Sanitize command output before storing or submitting activity documentation.

## Phoenix Activity Requirements

When coding activity creation, preserve these fields:

- `ticket_id`
- `start_datetime`
- `end_datetime`
- `summary`
- `root_cause`
- `actions_taken`
- `commands_summary`
- `validation_result`

`root_cause` must be the technical cause, not only the symptom.

`actions_taken` must list diagnosis and fix steps in order.

`commands_summary` must summarize relevant command classes without secret output.

`validation_result` must include concrete proof that the customer benefit is restored.

## Frontend Requirements

The frontend must support the technician workflow:

- ticket overview with title, customer, priority, and status
- sorting or filtering by date, priority, or status
- ticket detail with customer system information
- visible agent progress
- followable logs and actions
- approve, edit, reject, retry, and abort controls
- activity review before submission

Do not put privileged operations, Phoenix tokens, SSH keys, or raw secret-bearing logs in the browser.

## Backend Requirements

The backend owns:

- Phoenix API calls
- SSH execution
- safety checks
- audit logging
- agent orchestration
- activity generation
- secret handling

Phoenix workflow:

- `GET /api/v1/me/tickets`
- `GET /api/v1/tickets/{ticket_id}/customer-system`
- troubleshoot through approved SSH actions
- `POST /api/v1/activities/create`
- `PATCH /api/v1/tickets/{ticket_id}/status`

Handle `401`, `404`, validation errors, empty states, network failures, and timeouts without breaking the workflow.

## Verification Commands

Use the relevant checks after changes.

Full stack:

```bash
docker compose up --build
```

Backend local run:

```bash
cd backend
python -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app.main:app --reload
```

Frontend local run:

```bash
cd frontend
npm install
npm run dev
```

Frontend build:

```bash
cd frontend
npm run build
```

Backend health check:

```bash
curl http://localhost:8000/health
```

If tests or mocks are added, document and run their commands.

If a check cannot be run, say exactly why and what remains unverified.

## Working Process

Before coding, inspect the existing files related to the task.

Do not wander through unrelated files once enough context is available.

Make the smallest correct change.

After editing, verify with the narrowest relevant command first, then broader checks when needed.

Report changed files, checks run, and any remaining risk.

## When To Ask The User

Ask before proceeding if anything is unclear.

Ask before adding a dependency.

Ask before changing architecture.

Ask before changing public API shapes.

Ask before changing Docker, environment variable names, or secret handling.

Ask before implementing behavior not described in the docs.

Ask before making broad rewrites.

Ask before removing files or code that may still be used.

Ask when two valid approaches exist and the choice affects product behavior, safety, architecture, dependencies, or developer workflow.
