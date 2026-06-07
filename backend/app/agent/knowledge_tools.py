import json
from typing import Any

from pydantic import ValidationError as PydanticValidationError
from sqlmodel import Session

from app.core.errors import AppError
from app.core.redaction import redact_payload, redact_text
from app.db.session import engine
from app.repositories.runs import RunRepository
from app.schemas.knowledge import KnowledgeSearchRequest
from app.services.audit_log import AuditLog
from app.services.events import persist_and_publish_ws_event_sync
from app.services.knowledge import KnowledgeService


SEARCH_KNOWLEDGE_BASE_TOOL = {
    "type": "function",
    "function": {
        "name": "search_knowledge_base",
        "description": (
            "Search resolved service-desk knowledge snippets when you suspect a known issue type or want to check "
            "if a similar Linux service problem was solved before. Use it before proposing commands for familiar "
            "symptoms such as nginx 502, Bad Gateway storefront pages, status API unavailable, API is down, "
            "localhost health endpoint failures, disk full, failed systemd services, web-root permission problems, "
            "or MySQL startup failures."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Specific symptom, service, error, or suspected failure mode to search for."},
                "chunk_type": {
                    "type": "string",
                    "enum": ["problem", "diagnosis", "commands", "fix", "validation"],
                    "description": "Optional snippet type to narrow the search.",
                },
                "top_k": {"type": "integer", "default": 5, "minimum": 1, "maximum": 8},
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    },
}


def execute_search_knowledge_base(arguments: str | dict[str, Any], run_id: str | None = None) -> list[dict[str, Any]]:
    payload: dict[str, Any] = {}
    try:
        payload = json.loads(arguments) if isinstance(arguments, str) else dict(arguments)
        request = KnowledgeSearchRequest.model_validate(payload)
    except (json.JSONDecodeError, PydanticValidationError, TypeError, ValueError) as exc:
        result = [{"error": f"Invalid search_knowledge_base arguments: {redact_text(str(exc))}"}]
        _record_tool_event(run_id, payload if isinstance(payload, dict) else {}, result)
        return result

    try:
        with Session(engine) as session:
            results = KnowledgeService(session).search(request.query, chunk_type=request.chunk_type, top_k=request.top_k)
            safe_results = [
                redact_payload(
                    {
                        "chunk_type": result.chunk_type,
                        "content": _limit(result.content, 1200),
                        "ticket_id": result.ticket_id,
                        "similarity_score": result.similarity_score,
                    },
                    RunRepository(session).secrets,
                )
                for result in results
            ]
            _record_tool_event(run_id, request.model_dump(), safe_results)
            return safe_results
    except AppError as exc:
        result = [{"error": f"Knowledge search unavailable: {exc.message}"}]
        _record_tool_event(run_id, request.model_dump(), result)
        return result
    except Exception as exc:
        result = [{"error": f"Knowledge search unavailable: {redact_text(str(exc))}"}]
        _record_tool_event(run_id, request.model_dump(), result)
        return result


def _record_tool_event(run_id: str | None, request: dict[str, Any], results: list[dict[str, Any]]) -> None:
    if not run_id:
        return
    payload = {
        "query": request.get("query"),
        "chunk_type": request.get("chunk_type"),
        "top_k": request.get("top_k", 5),
        "result_count": len([result for result in results if "error" not in result]),
        "results": [
            {
                "ticket_id": result.get("ticket_id"),
                "chunk_type": result.get("chunk_type"),
                "similarity_score": result.get("similarity_score"),
                "preview": _limit(str(result.get("content") or result.get("error") or ""), 220),
            }
            for result in results[:5]
        ],
    }
    with Session(engine) as session:
        AuditLog(session).record("knowledge_search_performed", payload, run_id)
    persist_and_publish_ws_event_sync(run_id, "knowledge_search_performed", payload)


def _limit(value: str, limit: int) -> str:
    normalized = " ".join(value.split())
    if len(normalized) <= limit:
        return normalized
    return normalized[:limit].rstrip() + " [truncated]"
