# NoFlowCharts Technical Report

## Project

NoFlowCharts is an AI-assisted service desk autopilot for the techbold START Hack Vienna 2026 case. It is built around the required technician workflow: load assigned Phoenix ERP tickets, fetch the affected customer system, connect to the Ubuntu VM over SSH, diagnose and repair the incident with safety gates, validate the restored customer benefit, and submit structured activity documentation back to Phoenix.

The implementation is intentionally backend-owned for privileged operations. Phoenix tokens, SSH keys, SSH execution, safety checks, audit logging, LLM calls, activity generation, and memory persistence stay on the backend. The browser is a technician workspace, not a privileged execution environment.

## Case Alignment

The case study asks for a working web prototype that demonstrates the full loop live: load ticket, analyse, perform approved SSH actions, fix, validate, and submit the activity to ERP. The scoring rubric rewards functional ERP flow, troubleshooting performance, safety, human control, and reproducible engineering.

NoFlowCharts targets those scoring categories directly:

- Functional MVP: Phoenix-backed ticket queue, ticket detail, customer-system loading, run creation, activity draft/review/submit, and ticket status updates.
- Troubleshooting: LLM-backed diagnosis, execution, and verification phases that propose one command at a time and prefer evidence-backed root causes over guessing.
- Safety: command classification, hard blocking of dangerous patterns, redaction, audit events, bounded command execution, and explicit activity review before submission.
- Technician control: visible run state, SSH approval gate, terminal workflow, command accept/edit/reject/retry/comment controls, safer alternatives, validation confirmation, and abort.
- Engineering quality: separated modules for Phoenix API, SSH execution, safety, planning, terminal sessions, audit logging, activity generation, knowledge, metrics, and persistence.

## Tech Stack

NoFlowCharts is a full-stack web prototype with a backend-first security boundary.

- Frontend: React 18, TypeScript, Vite, Tailwind CSS 4, Radix UI/shadcn-style components, Lucide icons, and xterm.js for the browser terminal.
- Backend: Python, FastAPI, Uvicorn, Pydantic, SQLModel, SQLite, HTTPX, Paramiko, OpenAI Python SDK, and sqlite-vec.
- Persistence: SQLite stores runs, actions, command results, audit events, terminal transcripts, activity drafts, LLM metrics, ticket memories, and vector-searchable knowledge chunks.
- Realtime: WebSockets stream run events and terminal output to the technician console.
- ERP integration: Phoenix REST API is consumed only by the backend with bearer-token auth.
- SSH integration: Paramiko executes approved commands and opens controlled backend terminal sessions to the customer VM.
- AI provider: Azure OpenAI-compatible chat completions through the configured `AZURE_OPENAI_DEPLOYMENT`.
- Embeddings provider: Azure OpenAI-compatible embeddings through the configured `AZURE_OPENAI_EMBEDDING_DEPLOYMENT`, stored as 1536-dimensional vectors.

The exact Azure model names are deployment-configurable. The code does not hardcode a model ID; it reads the chat and embedding deployment names from environment variables so the same application can run against Azure OpenAI or an Azure Foundry project endpoint.

Model usage:

- Chat model deployment: used for diagnosis planning, execution planning, verification planning, final activity generation, semantic command safety review, and related-ticket reranking.
- Embedding model deployment: used for RAG knowledge chunks and ticket micro-memory similarity search.
- JSON mode: chat calls request structured JSON so command proposals and activity drafts can be validated before use.
- Tool calling: planning calls can invoke the knowledge-search tool before returning the final command proposal.

## Cost Model

The average LLM cost is about 25 cents per completed ticket. That includes command-planning calls, optional RAG/tool calls, semantic safety checks for non-read-only terminal commands, related-ticket reranking when memory candidates exist, and final activity generation.

This cost profile is acceptable for the case because the AI is doing high-leverage technician assistance: reducing diagnosis time, producing better ERP documentation, and preserving reusable knowledge. At managed-service scale, even a small reduction in repeated troubleshooting time easily outweighs a roughly $0.25 AI cost per resolved incident.

## Implemented Workflow

The frontend starts by loading the technician identity and assigned tickets from the backend, which proxies Phoenix ERP. The ticket queue supports search, status and priority filters, and sorting by date, priority, or customer.

When a ticket is opened, the technician can load the Phoenix customer-system information. This only fetches connection metadata. SSH is gated separately: the UI moves into an awaiting-approval state and the backend run is created only when the technician approves connection.

After approval, the backend creates a persisted run, sets the Phoenix ticket to `PENDING`, records the ticket/customer-system snapshots, and logs key events. The terminal bridge can then open a backend-owned SSH session for that run.

Troubleshooting proceeds through phases shown in the UI: diagnosis, fixing, recovery, verification, and final analysis. The terminal agent can propose commands from the diagnosis, execution, and verification agents. Proposed commands are safety-reviewed before display or execution.

The technician can accept, edit, reject, retry, or comment on agent proposals in the terminal. Manual terminal commands also pass through safety review and confirmation handling before execution. Mutating or risky actions are not silent background operations.

After evidence is collected, the technician confirms validation. The backend then generates a Phoenix activity draft from the run history, command results, terminal logs, validation evidence, and ticket context. The draft must contain the scored activity fields before review/submission.

Activity submission is explicit. The backend submits the activity to Phoenix and only then sets the ticket status to `DONE`.

## Backend Architecture

The backend is split by operational responsibility instead of one large agent module.

- Phoenix client: owns ERP calls, bearer-token auth, request timeouts, transient retries, response validation, and readable error mapping for auth, missing resources, and validation failures.
- SSH runner: executes one approved command at a time with connection timeout, command timeout, output truncation, and redacted errors.
- Terminal manager: owns run-scoped SSH terminal sessions, WebSocket streaming, persisted terminal logs, transcript capture, manual command review, agent proposal review, command timeouts, and run closure.
- Safety layer: deterministically classifies commands, blocks known-dangerous operations, and optionally performs semantic review for ambiguous non-read-only terminal commands.
- Planner: uses Azure OpenAI chat completions to produce one command proposal at a time for diagnosis, execution, or verification.
- Activity generator: turns the real run history into Phoenix activity fields after validation.
- Memory/RAG layer: stores resolved incident knowledge and ticket memories, retrieves relevant context, and passes only safe hints into planning.
- Audit and metrics: persist every key action, command decision, command result, activity transition, and LLM usage record.

The important design point is that the backend controls all privileged operations. The browser never receives the Phoenix token, SSH private key, or a direct path to execute commands on the customer machine.

## Frontend Architecture

The frontend is React, Vite, and TypeScript. It acts as a technician console rather than a privileged executor.

Verified UI capabilities include:

- Ticket queue with title, customer, priority, status, search, filters, and sort controls.
- Ticket workspace with overview, system, analysis, terminal, logs, and activity tabs.
- Customer report and ticket facts visible in the ticket overview.
- Customer-system panel loaded from backend/Phoenix.
- SSH approval dialog before backend run access.
- Agent phase progress indicator.
- Terminal using xterm with backend WebSocket bridge.
- Command review controls for accept, reject, edit, retry, and comment.
- Abort flow for stopping a run and closing active terminal state.
- Logs tab with audit and terminal command/transcript data.
- Activity draft editing, saving, review, validation handoff, and submit flow.
- Metrics cards for LLM usage, latency, command latency, and audit counts when backend telemetry is available.

## Agent Design

The planner is split into role-specific prompts instead of a single vague chatbot behavior:

- Diagnosis agent: identifies evidence and proposes read-only diagnostic commands until a concrete technical cause is supported.
- Execution agent: proposes the smallest targeted fix after diagnosis evidence exists.
- Verification agent: proves customer benefit is restored and checks persistence where relevant.
- Final analysis agent: generates structured Phoenix activity documentation from the actual run history.

The planner proposes exactly one shell command per step. Prompts explicitly prohibit assuming context, copying historical fixes blindly, reading secrets, deleting customer data, clearing logs, disabling security controls, broad filesystem changes, and compound shell commands.

The implementation also tracks anti-loop context: recent commands, repeated commands, rejected commands, technician guidance, and negative findings. This is meant to reduce wasted repeated probes and force the agent to use prior evidence.

## RAG And Memory System

The RAG system has two layers: general knowledge chunks and ticket-level micro-memories.

Resolved-ticket knowledge is split into five chunk types: problem, diagnosis, commands, fix, and validation. Each chunk is embedded with the configured Azure OpenAI embedding deployment and stored in SQLite through sqlite-vec as a 1536-dimensional vector. During planning, the agent can call a `search_knowledge_base` tool. The tool performs vector search first, falls back to keyword search if vector results are empty, and returns only the most relevant snippets.

The planner is told that retrieved knowledge is not an instruction. It is historical context only. This matters for safety and correctness: a similar ticket can suggest what to inspect, but the agent must still diagnose the current VM independently before fixing anything.

Ticket-level micro-memories are created after successful activity submission. Each completed ticket stores the title, description, root cause, actions taken, commands summary, validation result, sanitized commands, and an embedding. When a new ticket starts, the backend embeds the new ticket and retrieves up to five memory candidates. An LLM reranker then decides whether one candidate is truly technically related or whether the similarity is only generic outage wording.

If a related memory is selected, the planner receives that memory as context with strict instructions: do not assume the same root cause, do not copy historical commands blindly, and use the memory only to choose safer and more focused diagnostics. This allows the system to benefit from history without turning RAG into unsafe automation.

The current micro-memories are working. Because the hack setup only has five customer incidents, their immediate value is limited: with only five memories, they are often too sparse to materially change diagnosis. At larger service-desk scale, the same mechanism becomes much more valuable because every resolved ticket adds searchable, structured, technician-reviewed incident knowledge. That turns memory from a demo feature into a compounding operational asset.

## Safety Model

Safety is one of the central design goals. The case explicitly warns that unsafe operations can zero an incident or disqualify a team, so NoFlowCharts treats safety as a backend enforcement problem, not a prompt-only preference.

Commands are classified as read-only, mutating, risky mutating, or blocked. Blocked examples include broad `rm -rf`, dangerous recursive permissions, database deletion/reinitialization, firewall/audit/security disabling, log/history deletion, likely secret reads, nested shells, and unbounded interactive commands.

Every backend run starts with explicit SSH confirmation. Mutating and risky commands require review and, for high-risk forms, typed confirmation. Blocked commands cannot be approved. The technician can request a safer alternative instead of executing a blocked command.

The terminal path also safety-reviews manual commands and agent commands before execution. Read-only diagnosis may run automatically in the terminal agent to speed evidence collection, but machine-changing actions remain gated by the safety layer and technician review.

Secrets are redacted before logging, prompt construction, activity generation, and error reporting where configured secrets are known. SSH private keys and Phoenix tokens are backend-only and are not returned to the frontend.

The safety model has several layers:

- Access gate: loading customer-system metadata does not open SSH. The technician must approve backend SSH access for the run.
- Proposal gate: the agent proposes one command, not a script or open-ended plan. This keeps review understandable.
- Deterministic command gate: known-dangerous patterns are blocked before execution.
- Semantic safety gate: non-read-only terminal commands can be reviewed by an LLM safety reviewer that can allow, require confirmation, or block.
- Human control gate: the technician can accept, edit, reject, retry, comment, request a safer alternative, or abort.
- Execution gate: approved commands are rechecked before they run.
- Output gate: stdout/stderr are bounded, persisted, and redacted where configured secrets are known.
- Activity gate: final documentation is generated only after validation evidence exists and must be reviewed before submission.

Specific safety behavior includes:

- No broad recursive deletion on critical paths.
- No blanket world-writable permissions such as `chmod -R 777` on critical areas.
- No database deletion, reinitialization, or careless data removal.
- No disabling firewall, audit, AppArmor/SELinux, or similar security controls.
- No clearing logs or shell history to hide actions.
- No reading likely secret material such as private keys, `.env` files, or key files.
- No nested shells or unbounded interactive programs in the logged command path.
- No compound shell chains by default, because they hide multiple actions behind one approval.
- No superuser workaround pattern that bypasses the actual root cause.

The agent prompts mirror these same rules, but the backend does not rely on the model obeying them. If the model proposes something unsafe, the code can block it, show the reason, and allow the technician to request a safer alternative.

## Audit And Activity Documentation

The backend persists run state, actions, command results, terminal commands, terminal transcript events, WebSocket events, and audit events. Key audit events include ticket loading, customer-system loading, SSH confirmation, command classification, command proposals, approvals, edits, rejections, retries, blocked commands, command results, validation evidence, activity draft changes, activity review, activity submission, and ticket completion.

The final Phoenix activity draft is generated after validation evidence exists and must include:

- `summary`
- `root_cause`
- `actions_taken`
- `commands_summary`
- `validation_result`

The backend also includes `description` for Phoenix compatibility. The activity generator is instructed to write the technical root cause, diagnosis/fix/validation in chronological order, sanitized command classes, and concrete validation proof without secrets.

## Phoenix ERP Integration

The backend follows the Phoenix contract for technician identity, ticket queue, ticket detail, customer-system lookup, customer lookup, ticket status updates, activity creation, and environment reset. The local backend wraps those calls so the Phoenix bearer token stays server-side.

Phoenix ticket status is set to `PENDING` on run start and `DONE` only after activity submission succeeds. That keeps the ERP state aligned with the real service-desk workflow instead of marking work complete before validation and documentation are finished.

## Persistence And Reproducibility

The backend persists operational state in SQLite under the backend data directory by default. Persisted data includes runs, actions, command results, audit events, activity drafts, ticket memories, knowledge chunks, WebSocket replay events, terminal sessions, terminal commands, terminal transcripts, and LLM usage metrics.

The repository includes backend tests for the Phoenix client, safety layer, SSH runner, planner, providers, run manager, activity routes, ticket routes, WebSocket routes, terminal manager, knowledge, embeddings, ticket memory, metrics, repository behavior, write preview, audit log, and core behavior.

Environment variables are documented in `.env.example` and loaded through backend settings. Secrets are not expected in source control. Required runtime configuration includes Phoenix API settings, SSH key path/user, and Azure OpenAI settings when LLM features are used.

## Known Limitations

This is a hackathon prototype, not a production managed-service deployment.

Known limitations:

- Active runs are persisted for visibility and audit, but interrupted SSH command execution is not resumed after backend restart.
- The terminal agent can auto-run bounded read-only diagnostic steps; this improves speed but should be called out clearly because the case emphasizes explicit human approval for system actions.
- LLM and embedding features require configured Azure OpenAI credentials; without them, ticket loading and existing run inspection can still work, but agent features fail with configuration errors.
- Memory usefulness is limited by the tiny five-incident hack dataset, even though the mechanism is designed for larger-scale reuse.
- Full production concerns such as multi-tenancy, enterprise auth, compliance hardening, and deployment operations are outside this case scope.

## Demo Focus

The demo should focus less on route paths and more on the core proof: Phoenix ticket loading, SSH approval, safe agent-guided diagnosis, human-reviewed fix execution, concrete validation, audit visibility, and reviewed activity submission.

## Scoring Focus

The strongest parts of NoFlowCharts for judging are the backend safety boundary, auditability, structured activity generation, and service-desk workflow completeness. The implementation is built to avoid hardcoded incidents and instead use ticket context, live VM evidence, historical hints, and controlled command execution.

The main tradeoff is that the memory system is more valuable at real techbold scale than in the small hack dataset. With only five micro-memories, it works but has limited practical impact. With hundreds or thousands of resolved incidents, it becomes a strong advantage because similar tickets can surface prior root causes, command classes, validation patterns, and safe fix strategies without removing the technician from control.
