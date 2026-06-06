#!/usr/bin/env python3
"""
Phase 2 — BM25-first hybrid retrieval with AMC hard-routing and RRF fusion.

Strategy (PhaseWiseArchitecture.md §2):
- 75% BM25 + 25% bge-small-en vector via Reciprocal Rank Fusion
- AMC hard filter when AMC named in query
- Metadata re-ranking (financial density, content type, fund-name match)
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import faiss
import numpy as np
from rank_bm25 import BM25Okapi
from sentence_transformers import SentenceTransformer

from phase2.rag.chunking import ChunkMetadata
from phase2.rag.config import (
    AMC_ALIASES,
    BM25_WEIGHT,
    DEFAULT_TOP_K,
    EMBEDDING_MODEL,
    RRF_K,
    USE_RRF,
    VECTOR_WEIGHT,
)
from phase2.rag.fund_records import detect_query_metric, fund_name_matches, is_valid_scheme_name, mentions_out_of_corpus_amc


class EntityExtractor:
    """Extract entities from user queries for AMC routing and filtering."""

    def __init__(self) -> None:
        self.amc_aliases = AMC_ALIASES
        self.fund_types = [
            "index fund", "elss", "tax saving", "debt", "equity", "hybrid",
            "large cap", "mid cap", "small cap", "flexi cap", "multi cap",
            "liquid fund", "money market",
        ]
        self.financial_concepts = [
            "nav", "expense ratio", "exit load", "sip", "lump sum", "returns",
            "performance", "risk", "dividend", "growth", "direct plan", "regular plan",
            "minimum investment", "aum",
        ]

    def extract_entities(self, query: str) -> dict[str, list[str]]:
        query_lower = query.lower()
        entities: dict[str, list[str] | bool] = {
            "amcs": [],
            "amc_names": [],
            "fund_types": [],
            "concepts": [],
            "fund_names": [],
            "out_of_corpus_amc": False,
        }

        for alias, canonical in self.amc_aliases.items():
            if alias in query_lower and canonical not in entities["amc_names"]:
                entities["amcs"].append(alias)
                entities["amc_names"].append(canonical)

        for fund_type in self.fund_types:
            if fund_type in query_lower:
                entities["fund_types"].append(fund_type)

        for concept in self.financial_concepts:
            if concept in query_lower:
                entities["concepts"].append(concept)

        entities["out_of_corpus_amc"] = mentions_out_of_corpus_amc(query)

        fund_pattern = (
            r"\b((?:[A-Z][A-Za-z0-9&]*(?:\s+[A-Z][A-Za-z0-9&]*)*)\s+"
            r"(?:Index\s+Fund|Fund))\b"
        )
        for match in re.finditer(fund_pattern, query):
            name = match.group(1).strip()
            if name.lower() not in {a.lower() for a in self.amc_aliases} and not any(
                name.lower() == amc.lower() for amc in entities["amc_names"]
            ):
                if is_valid_scheme_name(name):
                    entities["fund_names"].append(name)
        return entities


def reciprocal_rank_fusion(
    ranked_lists: list[list[int]],
    *,
    k: int = RRF_K,
) -> dict[int, float]:
    """Merge ranked index lists using RRF."""
    scores: dict[int, float] = {}
    for ranks in ranked_lists:
        for rank, idx in enumerate(ranks):
            scores[idx] = scores.get(idx, 0.0) + 1.0 / (k + rank + 1)
    return scores


class HybridRetriever:
    """BM25-first hybrid retrieval with AMC hard-routing."""

    def __init__(
        self,
        model_name: str = EMBEDDING_MODEL,
        bm25_weight: float = BM25_WEIGHT,
        vector_weight: float = VECTOR_WEIGHT,
        use_rrf: bool = USE_RRF,
        rrf_k: int = RRF_K,
    ) -> None:
        self.model_name = model_name
        self.bm25_weight = bm25_weight
        self.vector_weight = vector_weight
        self.use_rrf = use_rrf
        self.rrf_k = rrf_k

        self.embedding_model = SentenceTransformer(model_name)
        self.entity_extractor = EntityExtractor()

        self.chunks: list[str] = []
        self.metadata: list[ChunkMetadata] = []
        self.bm25: BM25Okapi | None = None
        self.vector_index: faiss.Index | None = None
        self.chunk_embeddings: np.ndarray | None = None
        self.tokenized_corpus: list[list[str]] = []

    def load_chunks(self, chunks_file: Path) -> None:
        with open(chunks_file, encoding="utf-8") as f:
            chunks_data = json.load(f)

        self.chunks = []
        self.metadata = []
        for chunk_data in chunks_data:
            self.chunks.append(chunk_data["text"])
            self.metadata.append(ChunkMetadata(**chunk_data["metadata"]))

        print(f"Loaded {len(self.chunks)} chunks")

    def build_indexes(self) -> None:
        if not self.chunks:
            raise ValueError("No chunks loaded. Call load_chunks first.")

        self.tokenized_corpus = [chunk.lower().split() for chunk in self.chunks]
        self.bm25 = BM25Okapi(self.tokenized_corpus)

        print(f"Generating embeddings with {self.model_name}...")
        self.chunk_embeddings = self.embedding_model.encode(
            self.chunks,
            show_progress_bar=True,
            normalize_embeddings=True,
        )

        dimension = self.chunk_embeddings.shape[1]
        self.vector_index = faiss.IndexFlatIP(dimension)
        self.vector_index.add(self.chunk_embeddings.astype(np.float32))

        print(
            f"Built indexes: BM25 + FAISS FlatIP ({len(self.chunks)} vectors, dim={dimension})"
        )

    def _filter_by_amc(self, amc_names: list[str]) -> list[int]:
        indices: list[int] = []
        for idx, meta in enumerate(self.metadata):
            if any(name.lower() in meta.amc_name.lower() for name in amc_names):
                indices.append(idx)
        return indices

    def _filter_by_fund_type(self, fund_types: list[str], candidates: list[int]) -> list[int]:
        filtered: list[int] = []
        for idx in candidates:
            chunk_text = self.chunks[idx].lower()
            if any(ft in chunk_text for ft in fund_types):
                filtered.append(idx)
        return filtered

    def _filter_by_fund_name(self, fund_names: list[str], candidates: list[int]) -> list[int]:
        filtered: list[int] = []
        for idx in candidates:
            chunk_text = self.chunks[idx]
            meta = self.metadata[idx]
            if any(
                fund_name_matches(fn, chunk_text)
                or fund_name_matches(fn, meta.amc_name)
                or any(fund_name_matches(fn, entity) for entity in meta.entities)
                for fn in fund_names
            ):
                filtered.append(idx)
        return filtered

    def resolve_candidate_indices(
        self,
        entities: dict[str, list[str]],
    ) -> tuple[list[int], str]:
        """AMC hard-routing when AMC detected; optional fund-type/name narrowing."""
        if entities.get("out_of_corpus_amc"):
            return [], "out_of_corpus_amc"

        all_indices = list(range(len(self.chunks)))

        if entities["amc_names"]:
            amc_indices = self._filter_by_amc(entities["amc_names"])
            if amc_indices:
                candidates = amc_indices
                mode = "amc_hard"
            else:
                candidates = all_indices
                mode = "amc_fallback"
        else:
            candidates = all_indices
            mode = "full_corpus"

        if entities["fund_names"]:
            narrowed = self._filter_by_fund_name(entities["fund_names"], candidates)
            if narrowed:
                candidates = narrowed
                mode = f"{mode}+fund_name"

        elif entities["fund_types"]:
            if not entities["amc_names"] and not entities["fund_names"]:
                return [], "fund_type_without_corpus_anchor"
            narrowed = self._filter_by_fund_type(entities["fund_types"], candidates)
            if narrowed:
                candidates = narrowed
                mode = f"{mode}+fund_type"

        return candidates, mode

    def search_bm25(
        self,
        query: str,
        filtered_indices: list[int] | None = None,
    ) -> list[tuple[int, float]]:
        if self.bm25 is None:
            raise ValueError("BM25 index not built.")

        scores = self.bm25.get_scores(query.lower().split())
        if filtered_indices is not None:
            results = [(idx, float(scores[idx])) for idx in filtered_indices]
        else:
            results = [(idx, float(s)) for idx, s in enumerate(scores)]

        results.sort(key=lambda x: x[1], reverse=True)
        return results

    def search_vector(
        self,
        query: str,
        filtered_indices: list[int] | None = None,
        top_k: int = 100,
    ) -> list[tuple[int, float]]:
        if self.vector_index is None or self.chunk_embeddings is None:
            raise ValueError("Vector index not built.")

        query_embedding = self.embedding_model.encode(
            [query], normalize_embeddings=True
        ).astype(np.float32)

        if filtered_indices is not None and len(filtered_indices) < len(self.chunks):
            subset = self.chunk_embeddings[filtered_indices]
            sub_index = faiss.IndexFlatIP(subset.shape[1])
            sub_index.add(subset.astype(np.float32))
            scores, indices = sub_index.search(query_embedding, min(top_k, len(filtered_indices)))
            results = [
                (filtered_indices[int(idx)], float(scores[0][i]))
                for i, idx in enumerate(indices[0])
                if int(idx) >= 0
            ]
        else:
            scores, indices = self.vector_index.search(query_embedding, top_k)
            results = [
                (int(idx), float(scores[0][i]))
                for i, idx in enumerate(indices[0])
                if int(idx) >= 0
            ]

        results.sort(key=lambda x: x[1], reverse=True)
        return results

    def _apply_rerank_boosts(
        self,
        scores: dict[int, float],
        entities: dict[str, list[str]],
        query: str = "",
    ) -> dict[int, float]:
        boosted: dict[int, float] = {}
        metric = detect_query_metric(query) if query else None
        metric_tokens = {
            "nav": ("nav",),
            "aum": ("aum", "fund size"),
            "expense_ratio": ("expense ratio",),
            "exit_load": ("exit load",),
            "sip": ("minimum sip", "sip"),
            "minimum_investment": ("minimum lump", "minimum sip"),
            "returns": ("1y returns", "returns"),
        }.get(metric or "", ())

        for idx, score in scores.items():
            meta = self.metadata[idx]
            chunk_text = self.chunks[idx]
            chunk_lower = chunk_text.lower()
            multiplier = 1.0 + (meta.financial_density * 0.5)

            if meta.content_type == "fund_info":
                multiplier *= 1.2
            elif meta.content_type == "navigation":
                multiplier *= 0.5

            if entities["fund_names"]:
                if any(fund_name_matches(fn, chunk_text) for fn in entities["fund_names"]):
                    multiplier *= 1.5

            if metric_tokens and any(token in chunk_lower for token in metric_tokens):
                multiplier *= 1.4

            if metric == "aum" and entities["amc_names"] and "overview" in chunk_lower:
                multiplier *= 2.0

            if entities["amc_names"] and any(
                name.lower() in meta.amc_name.lower() for name in entities["amc_names"]
            ):
                multiplier *= 1.1

            boosted[idx] = score * multiplier
        return boosted

    def _combine_scores(
        self,
        bm25_results: list[tuple[int, float]],
        vector_results: list[tuple[int, float]],
    ) -> dict[int, float]:
        if self.use_rrf:
            bm25_ranks = [idx for idx, _ in bm25_results]
            vector_ranks = [idx for idx, _ in vector_results]
            return reciprocal_rank_fusion([bm25_ranks, vector_ranks], k=self.rrf_k)

        combined: dict[int, float] = {}
        for idx, score in bm25_results:
            combined[idx] = combined.get(idx, 0.0) + self.bm25_weight * score
        for idx, score in vector_results:
            combined[idx] = combined.get(idx, 0.0) + self.vector_weight * score
        return combined

    def hybrid_search(
        self,
        query: str,
        top_k: int = DEFAULT_TOP_K,
        apply_filtering: bool = True,
    ) -> list[dict[str, Any]]:
        entities = self.entity_extractor.extract_entities(query)

        if apply_filtering:
            candidates, filter_mode = self.resolve_candidate_indices(entities)
        else:
            candidates = list(range(len(self.chunks)))
            filter_mode = "none"

        if not candidates:
            return []

        print(f"Retrieval filter: {filter_mode} ({len(self.chunks)} → {len(candidates)} chunks)")

        bm25_results = self.search_bm25(query, candidates)
        vector_results = self.search_vector(query, candidates, top_k=max(top_k * 4, 20))

        combined = self._combine_scores(bm25_results, vector_results)
        combined = self._apply_rerank_boosts(combined, entities, query)

        sorted_results = sorted(combined.items(), key=lambda x: x[1], reverse=True)

        formatted: list[dict[str, Any]] = []
        for idx, score in sorted_results[:top_k]:
            meta = self.metadata[idx]
            formatted.append(
                {
                    "chunk_id": meta.chunk_id,
                    "text": self.chunks[idx],
                    "score": score,
                    "metadata": meta.model_dump(),
                    "source_id": meta.source_id,
                    "source_url": meta.source_url,
                    "amc_name": meta.amc_name,
                }
            )

        return formatted

    def save_index(self, output_dir: Path) -> None:
        output_dir.mkdir(parents=True, exist_ok=True)

        faiss.write_index(self.vector_index, str(output_dir / "vector_index.faiss"))
        np.save(output_dir / "chunk_embeddings.npy", self.chunk_embeddings)

        bm25_data = {
            "tokenized_corpus": self.tokenized_corpus,
            "chunks": self.chunks,
            "metadata": [meta.model_dump() for meta in self.metadata],
        }
        with open(output_dir / "bm25_data.json", "w", encoding="utf-8") as f:
            json.dump(bm25_data, f, indent=2)

        config = {
            "model_name": self.model_name,
            "bm25_weight": self.bm25_weight,
            "vector_weight": self.vector_weight,
            "use_rrf": self.use_rrf,
            "rrf_k": self.rrf_k,
            "total_chunks": len(self.chunks),
        }
        with open(output_dir / "retrieval_config.json", "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)

        print(f"Indexes saved to {output_dir}")

    @classmethod
    def load_index(cls, index_dir: Path) -> HybridRetriever:
        with open(index_dir / "retrieval_config.json", encoding="utf-8") as f:
            config = json.load(f)

        retriever = cls(
            model_name=config["model_name"],
            bm25_weight=config.get("bm25_weight", BM25_WEIGHT),
            vector_weight=config.get("vector_weight", VECTOR_WEIGHT),
            use_rrf=config.get("use_rrf", USE_RRF),
            rrf_k=config.get("rrf_k", RRF_K),
        )

        with open(index_dir / "bm25_data.json", encoding="utf-8") as f:
            bm25_data = json.load(f)

        retriever.chunks = bm25_data["chunks"]
        retriever.metadata = [ChunkMetadata(**meta) for meta in bm25_data["metadata"]]
        retriever.tokenized_corpus = bm25_data["tokenized_corpus"]
        retriever.bm25 = BM25Okapi(retriever.tokenized_corpus)
        retriever.vector_index = faiss.read_index(str(index_dir / "vector_index.faiss"))
        retriever.chunk_embeddings = np.load(index_dir / "chunk_embeddings.npy")

        print(f"Loaded {len(retriever.chunks)} chunks from {index_dir}")
        return retriever


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Phase 2 - Hybrid retrieval")
    parser.add_argument("--chunks", type=Path, required=True)
    parser.add_argument("--query", type=str, required=True)
    parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K)
    parser.add_argument("--build-index", action="store_true")
    parser.add_argument("--save-index", type=Path)
    parser.add_argument("--load-index", type=Path)
    args = parser.parse_args()

    if args.load_index:
        retriever = HybridRetriever.load_index(args.load_index)
    else:
        retriever = HybridRetriever()
        retriever.load_chunks(args.chunks)
        if args.build_index:
            retriever.build_indexes()
            if args.save_index:
                retriever.save_index(args.save_index)

    results = retriever.hybrid_search(args.query, top_k=args.top_k)

    print(f"\nQuery: {args.query}")
    print(f"Found {len(results)} results:\n")
    for i, result in enumerate(results, 1):
        print(f"{i}. Score: {result['score']:.4f}")
        print(f"   AMC: {result['amc_name']}")
        print(f"   Type: {result['metadata']['content_type']}")
        print(f"   Density: {result['metadata']['financial_density']:.3f}")
        print(f"   Text: {result['text'][:200]}...")
        print(f"   URL: {result['source_url']}\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
