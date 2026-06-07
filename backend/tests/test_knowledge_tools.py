from app.agent import knowledge_tools
from app.agent.knowledge_tools import execute_search_knowledge_base
from app.core.errors import AgentError


def test_search_knowledge_base_returns_tool_error_when_embeddings_fail(monkeypatch):
    events = []

    class FailingKnowledgeService:
        def __init__(self, session):
            pass

        def search(self, query, chunk_type=None, top_k=5):
            raise AgentError("Azure OpenAI embedding request failed: deployment missing")

    monkeypatch.setattr(knowledge_tools, "KnowledgeService", FailingKnowledgeService)
    monkeypatch.setattr(knowledge_tools, "_record_tool_event", lambda run_id, request, results: events.append((run_id, request, results)))

    result = execute_search_knowledge_base({"query": "nginx 502", "top_k": 1}, run_id="run-1")

    assert "Knowledge search unavailable" in result[0]["error"]
    assert events[0][0] == "run-1"
    assert events[0][2] == result
