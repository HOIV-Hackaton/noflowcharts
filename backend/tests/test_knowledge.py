from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.db.session import ensure_knowledge_vector_table
from app.repositories.knowledge import VECTOR_DIMENSIONS
from app.schemas.knowledge import KnowledgeIngestRequest, KnowledgeSeedItem
from app.services.knowledge import KnowledgeService


def make_session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    ensure_knowledge_vector_table(engine)
    return Session(engine)


class FakeEmbeddingProvider:
    def __init__(self):
        self.inputs = []

    def embed(self, text, timeout=20.0):
        self.inputs.append(text)
        vector = [0.0] * VECTOR_DIMENSIONS
        text_lower = text.lower()
        if "nginx" in text_lower or "502" in text_lower:
            vector[0] = 1.0
        elif "mysql" in text_lower:
            vector[1] = 1.0
        else:
            vector[2] = 1.0
        return vector


class ZeroEmbeddingProvider:
    def embed(self, text, timeout=20.0):
        return [0.0] * VECTOR_DIMENSIONS


def test_ingest_creates_five_resolved_ticket_chunks_and_replaces_existing_ticket_chunks():
    with make_session() as session:
        service = KnowledgeService(session, embedding_provider=FakeEmbeddingProvider())
        request = KnowledgeIngestRequest(
            ticket_id=7001,
            problem="nginx returns 502",
            diagnosis="upstream app was not listening",
            commands="systemctl status nginx returned active; curl returned 502",
            fix="started the upstream app service",
            validation="curl returned HTTP 200 ok",
        )

        first = service.ingest(request)
        second = service.ingest(request)

        assert first.inserted_count == 5
        assert second.inserted_count == 5
        results = service.search("nginx 502 upstream", top_k=8)
        assert len(results) == 5
        assert {result.chunk_type for result in results} == {"problem", "diagnosis", "commands", "fix", "validation"}


def test_seed_and_search_support_chunk_type_filter_and_ticket_id():
    with make_session() as session:
        service = KnowledgeService(session, embedding_provider=FakeEmbeddingProvider())
        service.seed(
            [
                KnowledgeSeedItem(ticket_id=7004, chunk_type="diagnosis", content="nginx 502 caused by stopped upstream service"),
                KnowledgeSeedItem(ticket_id=None, chunk_type="diagnosis", content="mysql failed to start because disk was full"),
                KnowledgeSeedItem(ticket_id=7004, chunk_type="validation", content="nginx health endpoint returned HTTP 200 ok"),
            ]
        )

        results = service.search("nginx 502 bad gateway", chunk_type="diagnosis", top_k=5)

        assert results[0].ticket_id == 7004
        assert results[0].chunk_type == "diagnosis"
        assert results[0].similarity_score > 0
        assert all(result.chunk_type == "diagnosis" for result in results)


def test_search_falls_back_to_keywords_when_vector_search_has_no_results():
    with make_session() as session:
        service = KnowledgeService(session, embedding_provider=FakeEmbeddingProvider())
        service.seed(
            [
                KnowledgeSeedItem(
                    ticket_id=7001,
                    chunk_type="diagnosis",
                    content="status API unavailable after reboot no listener on localhost 8080 missing systemd startup persistence",
                )
            ]
        )

        results = service.search("manual restart worked after reboot no listener 8080 service not enabled", chunk_type="diagnosis", top_k=5)

        assert results
        assert results[0].ticket_id == 7001
        assert "startup persistence" in results[0].content


def test_search_seeds_bundled_demo_knowledge_when_table_is_empty():
    with make_session() as session:
        service = KnowledgeService(session, embedding_provider=ZeroEmbeddingProvider())

        results = service.search(
            "Ubuntu status API localhost:8080/health unavailable after reboot service worked after manual restart "
            "known issue systemd service not enabled or wrong unit name",
            top_k=5,
        )

        assert results
        assert results[0].ticket_id == 7020
        assert any("after reboot" in result.content for result in results)
        assert any("wrong unit name" in result.content for result in results)
