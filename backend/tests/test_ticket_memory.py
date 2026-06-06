from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.db.models import ActivityDraft
from app.repositories.ticket_memory import RELATION_DECISION_NONE, RELATION_DECISION_RELATED, TicketMemoryRepository, cosine_similarity
from app.schemas.phoenix import Ticket, TicketStatus
from app.services.ticket_memory import TicketMemoryService, build_embedding_text


def make_session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def ticket(ticket_id=7001, title="Status API down", description="Customer reports 502 responses", status=TicketStatus.OPEN):
    return Ticket(
        id=ticket_id,
        title=title,
        description=description,
        priority="high",
        status=status,
        customer_id=5001,
        customer_name="Example GmbH",
    )


class FakeEmbeddingProvider:
    def __init__(self, vectors=None):
        self.vectors = vectors or [[1.0, 0.0, 0.0]]
        self.inputs = []

    def embed(self, text, timeout=20.0):
        self.inputs.append(text)
        index = min(len(self.inputs) - 1, len(self.vectors) - 1)
        return self.vectors[index]


class FakeLlmProvider:
    def __init__(self, payload=None, fail=False):
        self.payload = payload or {"decision": "none", "related_ticket_id": None, "rationale": "not related", "confidence": "low"}
        self.fail = fail
        self.messages = None

    def complete_json(self, messages, timeout=30.0):
        self.messages = messages
        if self.fail:
            raise RuntimeError("llm failed")
        return self.payload


def completed_draft():
    return ActivityDraft(
        run_id="run-1",
        summary="Restored the status API.",
        root_cause="nginx proxy used the wrong upstream port.",
        actions_taken="Checked nginx config, corrected port, and validated endpoint.",
        commands_summary="Used systemctl, config inspection, and curl validation.",
        validation_result="Health endpoint returned OK.",
        description="Restored API availability.",
    )


def add_completed(repo: TicketMemoryRepository, ticket_id: int, embedding: list[float], title="Prior API outage"):
    return repo.mark_completed(
        ticket_id=ticket_id,
        title=title,
        description="Status API returned 502",
        embedding=embedding,
        draft=completed_draft(),
        commands=["systemctl status nginx", "curl --max-time 5 -fsS http://localhost:8080/health"],
    )


def test_embedding_text_is_exact_unlabeled_title_description_join():
    assert build_embedding_text("Title", "Description") == "Title\n\nDescription"


def test_cosine_similarity_handles_nearest_vector():
    assert cosine_similarity([1, 0], [1, 0]) == 1.0
    assert cosine_similarity([1, 0], [0, 1]) == 0.0


def test_top_candidates_use_completed_memories_only_and_limit_to_five():
    with make_session() as session:
        repo = TicketMemoryRepository(session)
        repo.upsert_ticket_embedding(7002, "Open", "Not completed", [1.0, 0.0])
        for index in range(6):
            add_completed(repo, 7100 + index, [1.0, index / 10])
        add_completed(repo, 7001, [1.0, 0.0], title="Current ticket should be excluded")

        candidates = repo.list_top_candidates([1.0, 0.0], exclude_ticket_id=7001, limit=5)

        assert len(candidates) == 5
        assert 7002 not in [candidate.memory.ticket_id for candidate in candidates]
        assert 7001 not in [candidate.memory.ticket_id for candidate in candidates]


def test_prepare_ticket_relation_selects_llm_related_candidate():
    with make_session() as session:
        repo = TicketMemoryRepository(session)
        add_completed(repo, 7000, [1.0, 0.0, 0.0])
        llm = FakeLlmProvider({"decision": "related", "related_ticket_id": 7000, "rationale": "Same proxy symptom.", "confidence": "medium"})
        embeddings = FakeEmbeddingProvider([[1.0, 0.0, 0.0]])
        service = TicketMemoryService(session, embedding_provider=embeddings, llm_provider=llm)

        context = service.prepare_ticket_relation(ticket())

        assert embeddings.inputs == ["Status API down\n\nCustomer reports 502 responses"]
        assert context is not None
        assert context.ticket_id == 7000
        assert context.commands == ["systemctl status nginx", "curl --max-time 5 -fsS http://localhost:8080/health"]
        relation = repo.get_relation(7001)
        assert relation.decision == RELATION_DECISION_RELATED
        assert relation.related_ticket_id == 7000


def test_prepare_ticket_relation_stores_none_for_invalid_llm_selection():
    with make_session() as session:
        repo = TicketMemoryRepository(session)
        add_completed(repo, 7000, [1.0, 0.0])
        service = TicketMemoryService(
            session,
            embedding_provider=FakeEmbeddingProvider([[1.0, 0.0]]),
            llm_provider=FakeLlmProvider({"decision": "related", "related_ticket_id": 9999, "rationale": "bad id", "confidence": "high"}),
        )

        assert service.prepare_ticket_relation(ticket()) is None
        relation = repo.get_relation(7001)
        assert relation.decision == RELATION_DECISION_NONE
        assert relation.related_ticket_id is None


def test_prepare_ticket_relation_degrades_to_none_on_llm_failure():
    with make_session() as session:
        repo = TicketMemoryRepository(session)
        add_completed(repo, 7000, [1.0, 0.0])
        service = TicketMemoryService(session, embedding_provider=FakeEmbeddingProvider([[1.0, 0.0]]), llm_provider=FakeLlmProvider(fail=True))

        assert service.prepare_ticket_relation(ticket()) is None
        relation = repo.get_relation(7001)
        assert relation.decision == RELATION_DECISION_NONE


def test_none_relation_recomputes_for_open_ticket_but_not_done_ticket():
    with make_session() as session:
        repo = TicketMemoryRepository(session)
        relation = repo.upsert_relation(7001, None, RELATION_DECISION_NONE, "none", "low", 0)

        assert repo.should_recompute_relation(ticket(status=TicketStatus.OPEN), relation) is True
        assert repo.should_recompute_relation(ticket(status=TicketStatus.DONE), relation) is False


def test_create_completed_memory_uses_final_draft_and_exact_commands():
    with make_session() as session:
        service = TicketMemoryService(session, embedding_provider=FakeEmbeddingProvider([[0.0, 1.0]]), llm_provider=FakeLlmProvider())
        draft = completed_draft()

        memory = service.create_completed_memory(
            {"id": 7001, "title": "Status API down", "description": "Customer reports 502 responses"},
            draft,
            ["systemctl status nginx", "curl --max-time 5 -fsS http://localhost:8080/health"],
        )

        assert memory.status == "completed"
        assert memory.root_cause == draft.root_cause
        assert memory.commands == ["systemctl status nginx", "curl --max-time 5 -fsS http://localhost:8080/health"]
