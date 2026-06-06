"""Phase 3 HTTP API — request/response schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000, description="User question")


class QueryResponse(BaseModel):
    response: str
    citation: str = ""
    footer: str = ""
    educational_link: str = ""
    response_type: str
    intent: str
    confidence: float
    has_citation: bool
    has_grounded_answer: bool


class HealthResponse(BaseModel):
    status: str
    retriever_loaded: bool
    use_llm: bool
    groq_model: str
    phase2_dir: str
    load_error: str | None = None
    corpus_last_updated: str | None = None
