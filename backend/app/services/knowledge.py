from collections.abc import Iterable
import json
from pathlib import Path
from typing import Protocol

from sqlmodel import Session

from app.core.redaction import redact_payload
from app.db.models import ActivityDraft, Run
from app.repositories.knowledge import KnowledgeRepository, ScoredKnowledgeChunk
from app.repositories.runs import RunRepository
from app.schemas.knowledge import (
    KnowledgeChunkRead,
    KnowledgeChunkType,
    KnowledgeIngestRequest,
    KnowledgeIngestResponse,
    KnowledgeSearchResult,
    KnowledgeSeedItem,
    KnowledgeSeedResponse,
    ResolvedKnowledgeChunks,
)
from app.services.embeddings import AzureOpenAiEmbeddingProvider, get_embedding_provider


class EmbeddingProvider(Protocol):
    def embed(self, text: str, timeout: float = 20.0) -> list[float]:
        raise NotImplementedError


CHUNK_TYPES: tuple[KnowledgeChunkType, ...] = ("problem", "diagnosis", "commands", "fix", "validation")


class KnowledgeService:
    def __init__(self, session: Session, embedding_provider: EmbeddingProvider | None = None):
        self.session = session
        self.repo = KnowledgeRepository(session)
        self.embedding_provider = embedding_provider

    def ingest(self, request: KnowledgeIngestRequest, source: str = "resolved_ticket") -> KnowledgeIngestResponse:
        if source == "resolved_ticket":
            self.repo.delete_ticket_chunks(request.ticket_id, source=source)
        chunks = []
        for chunk_type in CHUNK_TYPES:
            content = getattr(request, chunk_type).strip()
            chunk = self.repo.add_chunk(
                ticket_id=request.ticket_id,
                source=source,
                chunk_type=chunk_type,
                content=content,
                embedding=self._embed(content),
            )
            chunks.append(KnowledgeChunkRead.model_validate(chunk, from_attributes=True))
        return KnowledgeIngestResponse(inserted_count=len(chunks), chunks=chunks)

    def seed(self, items: Iterable[KnowledgeSeedItem]) -> KnowledgeSeedResponse:
        self.repo.delete_seed_chunks()
        chunks = []
        for item in items:
            content = item.content.strip()
            chunk = self.repo.add_chunk(
                ticket_id=item.ticket_id,
                source="seed",
                chunk_type=item.chunk_type,
                content=content,
                embedding=self._embed(content),
            )
            chunks.append(KnowledgeChunkRead.model_validate(chunk, from_attributes=True))
        return KnowledgeSeedResponse(inserted_count=len(chunks), chunks=chunks)

    def search(self, query: str, chunk_type: KnowledgeChunkType | None = None, top_k: int = 5) -> list[KnowledgeSearchResult]:
        limit = max(1, min(top_k, 8))
        if self.repo.count_chunks() == 0:
            self._seed_bundled_demo_knowledge()
        scored = self.repo.search(self._embed(query), chunk_type=chunk_type, limit=limit)
        if not scored:
            scored = self.repo.keyword_search(query, chunk_type=chunk_type, limit=limit)
        if not scored:
            self._seed_bundled_demo_knowledge()
            scored = self.repo.keyword_search(query, chunk_type=chunk_type, limit=limit)
        return [self._search_result(item) for item in scored]

    def ingest_resolved_run(self, run: Run, draft: ActivityDraft) -> KnowledgeIngestResponse | None:
        snapshot = run.customer_system_snapshot or {}
        ticket = snapshot.get("ticket") or {}
        if not ticket:
            return None
        chunks = build_resolved_knowledge_chunks(run, draft, RunRepository(self.session))
        return self.ingest(
            KnowledgeIngestRequest(
                ticket_id=chunks.ticket_id,
                problem=chunks.problem,
                diagnosis=chunks.diagnosis,
                commands=chunks.commands,
                fix=chunks.fix,
                validation=chunks.validation,
            )
        )

    def _embed(self, text: str) -> list[float]:
        provider = self.embedding_provider or get_embedding_provider()
        return provider.embed(text)

    def _search_result(self, scored: ScoredKnowledgeChunk) -> KnowledgeSearchResult:
        chunk = scored.chunk
        return KnowledgeSearchResult(
            chunk_type=chunk.chunk_type,
            content=chunk.content,
            ticket_id=chunk.ticket_id,
            similarity_score=round(scored.similarity_score, 6),
        )

    def _seed_bundled_demo_knowledge(self) -> None:
        seed_path = Path(__file__).resolve().parents[2] / "seed_knowledge.json"
        if not seed_path.exists():
            return
        items = [KnowledgeSeedItem.model_validate(item) for item in json.loads(seed_path.read_text(encoding="utf-8"))]
        self.seed(items)


def build_resolved_knowledge_chunks(run: Run, draft: ActivityDraft, repo: RunRepository) -> ResolvedKnowledgeChunks:
    snapshot = run.customer_system_snapshot or {}
    ticket = snapshot.get("ticket") or {}
    ticket_id = int(ticket.get("id") or run.ticket_id)
    title = str(ticket.get("title") or "")
    description = str(ticket.get("description") or "")
    command_evidence = _command_evidence(run.id, repo)
    problem = _join_sections(title, description)
    diagnosis = _join_sections(draft.root_cause, _diagnostic_actions(draft.actions_taken), command_evidence)
    commands = _join_sections(draft.commands_summary, command_evidence)
    fix = _join_sections(draft.actions_taken, f"Why: {draft.root_cause}" if draft.root_cause else None)
    validation = _join_sections(draft.validation_result, _validation_evidence(run.id, repo))
    return ResolvedKnowledgeChunks(
        ticket_id=ticket_id,
        problem=problem,
        diagnosis=diagnosis,
        commands=commands,
        fix=fix,
        validation=validation,
    )


def _join_sections(*values: str | None) -> str:
    return "\n\n".join(str(value).strip() for value in values if str(value or "").strip())


def _diagnostic_actions(actions_taken: str | None) -> str | None:
    if not actions_taken:
        return None
    return f"Diagnosis and findings: {actions_taken}"


def _command_evidence(run_id: str, repo: RunRepository) -> str:
    lines: list[str] = []
    for result in repo.list_command_results(run_id):
        output = _compact_output(_join_sections(result.stdout, result.stderr))
        lines.append(f"Command: {result.command}\nExit: {result.exit_code}; timed_out: {result.timed_out}\nOutput: {output}")
    for command in repo.list_terminal_commands(run_id):
        if command.exit_code is None:
            continue
        selected = command.final_command or command.original_command
        output = _compact_output(command.output)
        lines.append(f"Command: {selected}\nExit: {command.exit_code}\nOutput: {output}")
    return "\n\n".join(str(redact_payload(line, repo.secrets)) for line in lines)


def _validation_evidence(run_id: str, repo: RunRepository) -> str:
    validation_lines = []
    for result in repo.list_command_results(run_id):
        command = result.command.lower()
        output = f"{result.stdout}\n{result.stderr}".lower()
        if any(term in command or term in output for term in ("curl", "health", "is-active", "smoke", "validation", "http 200", "ok")):
            validation_lines.append(f"Validation command: {result.command}\nExit: {result.exit_code}\nOutput: {_compact_output(_join_sections(result.stdout, result.stderr))}")
    for command in repo.list_terminal_commands(run_id):
        selected = command.final_command or command.original_command
        text = f"{selected}\n{command.output}".lower()
        if command.exit_code == 0 and any(term in text for term in ("curl", "health", "is-active", "smoke", "validation", "http 200", "ok")):
            validation_lines.append(f"Validation command: {selected}\nExit: {command.exit_code}\nOutput: {_compact_output(command.output)}")
    return "\n\n".join(str(redact_payload(line, repo.secrets)) for line in validation_lines)


def _compact_output(output: str | None, limit: int = 800) -> str:
    compact = " ".join(str(output or "").split())
    if not compact:
        return "<empty>"
    if len(compact) > limit:
        return compact[:limit].rstrip() + " [truncated]"
    return compact


def get_knowledge_service(session: Session) -> KnowledgeService:
    return KnowledgeService(session, embedding_provider=AzureOpenAiEmbeddingProvider())
