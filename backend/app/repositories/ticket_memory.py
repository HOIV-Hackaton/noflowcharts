import math
from dataclasses import dataclass

from sqlmodel import Session, select

from app.db.models import ActivityDraft, TicketMemory, TicketRelation, utc_now
from app.schemas.phoenix import Ticket, TicketStatus


MEMORY_STATUS_INDEXED = "indexed"
MEMORY_STATUS_COMPLETED = "completed"
RELATION_DECISION_RELATED = "related"
RELATION_DECISION_NONE = "none"


@dataclass(frozen=True)
class ScoredTicketMemory:
    memory: TicketMemory
    score: float


class TicketMemoryRepository:
    def __init__(self, session: Session):
        self.session = session

    def upsert_ticket_embedding(
        self,
        ticket_id: int,
        title: str,
        description: str,
        embedding: list[float],
        status: str = MEMORY_STATUS_INDEXED,
    ) -> TicketMemory:
        memory = self.session.get(TicketMemory, ticket_id)
        now = utc_now()
        if memory is None:
            memory = TicketMemory(ticket_id=ticket_id, created_at=now)
        memory.title = title
        memory.description = description
        memory.embedding = embedding
        if memory.status != MEMORY_STATUS_COMPLETED:
            memory.status = status
        memory.updated_at = now
        self.session.add(memory)
        self.session.commit()
        self.session.refresh(memory)
        return memory

    def mark_completed(
        self,
        ticket_id: int,
        title: str,
        description: str,
        embedding: list[float],
        draft: ActivityDraft,
        commands: list[str],
    ) -> TicketMemory:
        memory = self.session.get(TicketMemory, ticket_id)
        now = utc_now()
        if memory is None:
            memory = TicketMemory(ticket_id=ticket_id, created_at=now)
        memory.title = title
        memory.description = description
        memory.embedding = embedding
        memory.status = MEMORY_STATUS_COMPLETED
        memory.activity_summary = draft.summary
        memory.root_cause = draft.root_cause
        memory.actions_taken = draft.actions_taken
        memory.commands_summary = draft.commands_summary
        memory.validation_result = draft.validation_result
        memory.commands = commands
        memory.updated_at = now
        memory.solved_at = now
        self.session.add(memory)
        self.session.commit()
        self.session.refresh(memory)
        return memory

    def get_memory(self, ticket_id: int) -> TicketMemory | None:
        return self.session.get(TicketMemory, ticket_id)

    def list_completed_memories(self, exclude_ticket_id: int | None = None) -> list[TicketMemory]:
        statement = select(TicketMemory).where(TicketMemory.status == MEMORY_STATUS_COMPLETED)
        if exclude_ticket_id is not None:
            statement = statement.where(TicketMemory.ticket_id != exclude_ticket_id)
        return list(self.session.exec(statement))

    def list_top_candidates(self, embedding: list[float], exclude_ticket_id: int, limit: int = 5) -> list[ScoredTicketMemory]:
        scored = []
        for memory in self.list_completed_memories(exclude_ticket_id=exclude_ticket_id):
            score = cosine_similarity(embedding, memory.embedding)
            scored.append(ScoredTicketMemory(memory=memory, score=score))
        return sorted(scored, key=lambda item: item.score, reverse=True)[:limit]

    def get_relation(self, ticket_id: int) -> TicketRelation | None:
        return self.session.get(TicketRelation, ticket_id)

    def upsert_relation(
        self,
        ticket_id: int,
        related_ticket_id: int | None,
        decision: str,
        rationale: str | None,
        confidence: str | None,
        candidate_count: int,
    ) -> TicketRelation:
        relation = self.session.get(TicketRelation, ticket_id)
        now = utc_now()
        if relation is None:
            relation = TicketRelation(ticket_id=ticket_id, created_at=now)
        relation.related_ticket_id = related_ticket_id
        relation.decision = decision
        relation.rationale = rationale
        relation.confidence = confidence
        relation.candidate_count = candidate_count
        relation.updated_at = now
        self.session.add(relation)
        self.session.commit()
        self.session.refresh(relation)
        return relation

    def should_recompute_relation(self, ticket: Ticket, relation: TicketRelation | None) -> bool:
        if relation is None:
            return True
        if relation.decision == RELATION_DECISION_NONE and ticket.status != TicketStatus.DONE:
            return True
        return False


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot / (left_norm * right_norm)
