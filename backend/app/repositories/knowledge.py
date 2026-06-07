from dataclasses import dataclass
import re

from sqlalchemy import delete, text
from sqlmodel import Session, select

from app.core.errors import DatabaseError, ValidationError
from app.db.models import KnowledgeChunk, utc_now
from app.schemas.knowledge import KnowledgeChunkType


VECTOR_DIMENSIONS = 1536


@dataclass(frozen=True)
class ScoredKnowledgeChunk:
    chunk: KnowledgeChunk
    distance: float

    @property
    def similarity_score(self) -> float:
        return 1.0 / (1.0 + max(0.0, self.distance))


class KnowledgeRepository:
    def __init__(self, session: Session):
        self.session = session
        self._ensure_schema()

    def add_chunk(
        self,
        *,
        ticket_id: int | None,
        source: str,
        chunk_type: KnowledgeChunkType,
        content: str,
        embedding: list[float],
    ) -> KnowledgeChunk:
        self._validate_embedding(embedding)
        chunk = KnowledgeChunk(
            ticket_id=ticket_id,
            source=source,
            chunk_type=chunk_type,
            content=content.strip(),
            created_at=utc_now(),
        )
        self.session.add(chunk)
        self.session.commit()
        self.session.refresh(chunk)
        assert chunk.id is not None
        self.session.execute(
            text("INSERT OR REPLACE INTO knowledge_chunk_vectors(rowid, embedding) VALUES (:rowid, :embedding)"),
            {"rowid": chunk.id, "embedding": serialize_embedding(embedding)},
        )
        self.session.commit()
        return chunk

    def delete_ticket_chunks(self, ticket_id: int, source: str = "resolved_ticket") -> int:
        chunks = list(
            self.session.exec(
                select(KnowledgeChunk).where(KnowledgeChunk.ticket_id == ticket_id, KnowledgeChunk.source == source)
            )
        )
        if not chunks:
            return 0
        chunk_ids = [chunk.id for chunk in chunks if chunk.id is not None]
        for chunk_id in chunk_ids:
            self.session.execute(text("DELETE FROM knowledge_chunk_vectors WHERE rowid = :rowid"), {"rowid": chunk_id})
        self.session.exec(delete(KnowledgeChunk).where(KnowledgeChunk.id.in_(chunk_ids)))
        self.session.commit()
        return len(chunk_ids)

    def search(
        self,
        embedding: list[float],
        *,
        chunk_type: KnowledgeChunkType | None = None,
        limit: int = 5,
    ) -> list[ScoredKnowledgeChunk]:
        self._validate_embedding(embedding)
        vector = serialize_embedding(embedding)
        rows = self.session.execute(
            text(
                "SELECT rowid, distance FROM knowledge_chunk_vectors "
                "WHERE embedding MATCH :embedding AND k = :limit "
                "ORDER BY distance"
            ),
            {"embedding": vector, "limit": max(1, min(limit * 4 if chunk_type else limit, 32))},
        ).all()
        scored: list[ScoredKnowledgeChunk] = []
        for row in rows:
            chunk_id = int(row[0])
            distance = float(row[1])
            chunk = self.session.get(KnowledgeChunk, chunk_id)
            if chunk is None:
                continue
            if chunk_type is not None and chunk.chunk_type != chunk_type:
                continue
            scored.append(ScoredKnowledgeChunk(chunk=chunk, distance=distance))
            if len(scored) >= limit:
                break
        return scored

    def count_chunks(self) -> int:
        return len(list(self.session.exec(select(KnowledgeChunk.id))))

    def keyword_search(self, query: str, *, chunk_type: KnowledgeChunkType | None = None, limit: int = 5) -> list[ScoredKnowledgeChunk]:
        query_terms = _keyword_terms(query)
        if not query_terms:
            return []
        statement = select(KnowledgeChunk)
        if chunk_type is not None:
            statement = statement.where(KnowledgeChunk.chunk_type == chunk_type)
        scored: list[tuple[int, KnowledgeChunk]] = []
        for chunk in self.session.exec(statement):
            content_terms = set(_keyword_terms(chunk.content))
            matches = sum(1 for term in query_terms if term in content_terms)
            if matches:
                scored.append((matches, chunk))
        scored.sort(key=lambda item: (item[0], item[1].ticket_id or 0), reverse=True)
        return [ScoredKnowledgeChunk(chunk=chunk, distance=1.0 / matches) for matches, chunk in scored[: max(1, limit)]]

    def delete_seed_chunks(self) -> int:
        chunks = list(self.session.exec(select(KnowledgeChunk).where(KnowledgeChunk.source == "seed")))
        if not chunks:
            return 0
        chunk_ids = [chunk.id for chunk in chunks if chunk.id is not None]
        for chunk_id in chunk_ids:
            self.session.execute(text("DELETE FROM knowledge_chunk_vectors WHERE rowid = :rowid"), {"rowid": chunk_id})
        self.session.exec(delete(KnowledgeChunk).where(KnowledgeChunk.id.in_(chunk_ids)))
        self.session.commit()
        return len(chunk_ids)

    def _validate_embedding(self, embedding: list[float]) -> None:
        if len(embedding) != VECTOR_DIMENSIONS:
            raise ValidationError(f"Knowledge embeddings must have {VECTOR_DIMENSIONS} dimensions")

    def _ensure_schema(self) -> None:
        connection = self.session.connection()
        raw_connection = getattr(connection.connection, "driver_connection", None)
        if raw_connection is not None:
            try:
                raw_connection.execute("select vec_version()")
            except Exception:
                import sqlite_vec

                raw_connection.enable_load_extension(True)
                try:
                    sqlite_vec.load(raw_connection)
                finally:
                    raw_connection.enable_load_extension(False)
        self.session.execute(
            text(
                "CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_chunk_vectors "
                "USING vec0(embedding float[1536])"
            )
        )


def serialize_embedding(embedding: list[float]) -> bytes:
    try:
        from sqlite_vec import serialize_float32
    except Exception as exc:
        raise DatabaseError("sqlite-vec is not installed; install backend requirements") from exc
    return serialize_float32(embedding)


def _keyword_terms(value: str) -> list[str]:
    terms = []
    for term in re.findall(r"[a-z0-9][a-z0-9._:/-]*", value.lower()):
        if len(term) < 3 or term in {"the", "and", "for", "with", "that", "this", "was", "are", "not", "but", "after", "before"}:
            continue
        terms.append(term)
    return terms
