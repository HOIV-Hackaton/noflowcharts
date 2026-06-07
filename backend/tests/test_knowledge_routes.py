from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.api import routes_knowledge
from app.main import app
from app.schemas.knowledge import KnowledgeChunkRead, KnowledgeIngestResponse, KnowledgeSeedResponse, KnowledgeSearchResult


class FakeKnowledgeService:
    def ingest(self, request):
        return KnowledgeIngestResponse(inserted_count=5, chunks=[_chunk("problem", request.problem)])

    def seed(self, items):
        items = list(items)
        return KnowledgeSeedResponse(inserted_count=len(items), chunks=[_chunk(items[0].chunk_type, items[0].content)])

    def search(self, query, chunk_type=None, top_k=5):
        return [KnowledgeSearchResult(chunk_type=chunk_type or "diagnosis", content=f"match for {query}", ticket_id=7004, similarity_score=0.9)]


def _chunk(chunk_type, content):
    return KnowledgeChunkRead(
        id=1,
        ticket_id=7004,
        source="seed",
        chunk_type=chunk_type,
        content=content,
        created_at=datetime.now(UTC),
    )


def test_knowledge_routes_ingest_seed_and_search():
    app.dependency_overrides[routes_knowledge.get_knowledge_service_dependency] = lambda: FakeKnowledgeService()
    try:
        client = TestClient(app)
        ingest = client.post(
            "/api/knowledge/ingest",
            json={
                "ticket_id": 7004,
                "problem": "p",
                "diagnosis": "d",
                "commands": "c",
                "fix": "f",
                "validation": "v",
            },
        )
        seed = client.post("/api/knowledge/seed", json={"items": [{"ticket_id": 7004, "chunk_type": "problem", "content": "nginx 502"}]})
        search = client.post("/api/knowledge/search", json={"query": "nginx 502", "chunk_type": "diagnosis", "top_k": 5})

        assert ingest.status_code == 200
        assert ingest.json()["inserted_count"] == 5
        assert seed.status_code == 200
        assert seed.json()["inserted_count"] == 1
        assert search.status_code == 200
        assert search.json()[0]["ticket_id"] == 7004
    finally:
        app.dependency_overrides.clear()
