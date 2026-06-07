from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


KnowledgeChunkType = Literal["problem", "diagnosis", "commands", "fix", "validation"]


class KnowledgeIngestRequest(BaseModel):
    ticket_id: int
    problem: str = Field(min_length=1)
    diagnosis: str = Field(min_length=1)
    commands: str = Field(min_length=1)
    fix: str = Field(min_length=1)
    validation: str = Field(min_length=1)


class KnowledgeSeedItem(BaseModel):
    ticket_id: int | None = None
    chunk_type: KnowledgeChunkType
    content: str = Field(min_length=1)


class KnowledgeSeedRequest(BaseModel):
    items: list[KnowledgeSeedItem] = Field(min_length=1)


class KnowledgeSearchRequest(BaseModel):
    query: str = Field(min_length=1)
    chunk_type: KnowledgeChunkType | None = None
    top_k: int = 5

    @field_validator("top_k")
    @classmethod
    def cap_top_k(cls, value: int) -> int:
        if value < 1:
            return 1
        if value > 8:
            return 8
        return value


class KnowledgeChunkRead(BaseModel):
    id: int
    ticket_id: int | None
    source: str
    chunk_type: KnowledgeChunkType
    content: str
    created_at: datetime


class KnowledgeIngestResponse(BaseModel):
    inserted_count: int
    chunks: list[KnowledgeChunkRead]


class KnowledgeSearchResult(BaseModel):
    chunk_type: KnowledgeChunkType
    content: str
    ticket_id: int | None
    similarity_score: float


class KnowledgeSeedResponse(BaseModel):
    inserted_count: int
    chunks: list[KnowledgeChunkRead]


class ResolvedKnowledgeChunks(BaseModel):
    ticket_id: int
    problem: str
    diagnosis: str
    commands: str
    fix: str
    validation: str

    @model_validator(mode="after")
    def require_all_chunks(self):
        missing = [field for field in ("problem", "diagnosis", "commands", "fix", "validation") if not getattr(self, field).strip()]
        if missing:
            raise ValueError(f"resolved knowledge is missing chunk(s): {', '.join(missing)}")
        return self
