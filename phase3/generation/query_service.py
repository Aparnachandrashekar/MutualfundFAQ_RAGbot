#!/usr/bin/env python3
"""
Phase 3 — Query service orchestrating retrieval and generation.

Shared by the CLI pipeline and the HTTP API backend.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from phase2.rag.config import DEFAULT_TOP_K

from .answer_generator import AnswerGenerator
from .config import GROQ_MODEL, PHASE2_DIR
from .corpus_meta import read_corpus_data_as_of, sync_ui_corpus_meta


def load_phase2_retriever(phase2_dir: Path):
    """Load the Phase 2 hybrid retriever from disk."""
    try:
        from phase2.rag.retrieval import HybridRetriever

        retrieval_dir = phase2_dir / "retrieval"
        if not retrieval_dir.exists():
            return None
        return HybridRetriever.load_index(retrieval_dir)
    except Exception:
        return None


def _resolve_use_llm(use_llm: bool | None) -> bool:
    if use_llm is not None:
        return use_llm
    env_flag = os.environ.get("USE_LLM", "").strip().lower()
    if env_flag in ("1", "true", "yes"):
        return True
    if env_flag in ("0", "false", "no"):
        return False
    return False


class QueryService:
    """End-to-end query handler: intent → retrieval → generation → guardrails."""

    def __init__(
        self,
        phase2_dir: Path | None = None,
        use_llm: bool | None = None,
        top_k: int = DEFAULT_TOP_K,
        groq_model: str = GROQ_MODEL,
    ) -> None:
        self.phase2_dir = Path(phase2_dir or PHASE2_DIR)
        self.use_llm = _resolve_use_llm(use_llm)
        self.top_k = top_k
        self.groq_model = groq_model
        self._retriever = None
        self._generator: AnswerGenerator | None = None
        self._load_error: str | None = None

    @property
    def retriever_loaded(self) -> bool:
        return self._retriever is not None

    @property
    def load_error(self) -> str | None:
        return self._load_error

    def initialize(self, *, eager_retriever: bool = False) -> None:
        """Prepare the service. Retriever loads lazily unless eager_retriever=True."""
        sync_ui_corpus_meta(self.phase2_dir)
        if eager_retriever:
            self._ensure_generator()
            self._ensure_retriever()

    def _index_present(self) -> bool:
        index_dir = self.phase2_dir / "retrieval"
        return (index_dir / "retrieval_config.json").is_file()

    def _ensure_generator(self) -> AnswerGenerator:
        if self._generator is None:
            self._generator = AnswerGenerator(
                model_name=self.groq_model,
                use_llm=self.use_llm,
            )
        return self._generator

    def _ensure_retriever(self) -> None:
        if self._retriever is None and self._load_error is None:
            try:
                self._retriever = load_phase2_retriever(self.phase2_dir)
                if self._retriever is None:
                    self._load_error = f"Retrieval index not found at {self.phase2_dir / 'retrieval'}"
            except Exception as exc:
                self._load_error = str(exc)

    def handle_query(self, query: str) -> dict[str, Any]:
        """Process a user query and return a guardrails-compliant response dict."""
        query = query.strip()
        if not query:
            raise ValueError("Query must not be empty")

        generator = self._ensure_generator()
        self._ensure_retriever()

        retrieved_chunks: list[dict[str, Any]] = []
        if self._retriever is not None and not generator.is_query_out_of_scope(query):
            retrieved_chunks = self._retriever.hybrid_search(query, top_k=self.top_k)

        return generator.generate_response(
            query,
            retrieved_chunks,
            use_llm=self.use_llm,
        )

    def corpus_last_updated(self) -> str | None:
        """Return YYYY-MM-DD for the newest indexed corpus snapshot."""
        return read_corpus_data_as_of(self.phase2_dir)

    def health_status(self) -> dict[str, Any]:
        """Return service health metadata for the /health endpoint."""
        index_present = self._index_present()
        if self._load_error:
            status = "degraded"
        elif not index_present:
            status = "degraded"
        else:
            status = "ok"
        return {
            "status": status,
            "retriever_loaded": self.retriever_loaded,
            "index_present": index_present,
            "use_llm": self.use_llm,
            "groq_model": self.groq_model,
            "phase2_dir": str(self.phase2_dir),
            "load_error": self._load_error,
            "corpus_last_updated": self.corpus_last_updated(),
        }
