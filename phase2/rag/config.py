"""Phase 2 retrieval and chunking defaults (aligned with PhaseWiseArchitecture.md)."""

from __future__ import annotations

import os

# Embedding model — same family as Phase 1.5 validation
EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"

# Hybrid retrieval: BM25-first for sparse financial keyword data
BM25_WEIGHT = 0.75
VECTOR_WEIGHT = 0.25
USE_RRF = True
RRF_K = 60

# Chunking
MIN_CHUNK_SIZE = 300
MAX_CHUNK_SIZE = 400
CHUNK_OVERLAP = 50
MIN_FINANCIAL_DENSITY = 0.05
MIN_SOURCE_VALIDATION_QUALITY = 0.05

# Retrieval
DEFAULT_TOP_K = 5
FAISS_INDEX_TYPE = "flat"

# Render Starter (512MB): set RETRIEVAL_MODE=bm25_only to skip torch/sentence-transformers.
RETRIEVAL_MODE = os.environ.get("RETRIEVAL_MODE", "hybrid").strip().lower()
BM25_ONLY_MODE = RETRIEVAL_MODE in ("bm25", "bm25_only")

# AMC aliases → canonical amc_name (for hard routing)
AMC_ALIASES: dict[str, str] = {
    "choice": "Choice Mutual Fund",
    "unifi": "Unifi Mutual Fund",
    "union": "Union Mutual Fund",
    "icici prudential": "ICICI Prudential Mutual Fund",
    "icici": "ICICI Prudential Mutual Fund",
    "lic": "LIC Mutual Fund",
}
