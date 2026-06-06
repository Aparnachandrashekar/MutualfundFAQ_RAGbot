#!/usr/bin/env python3
"""
Phase 2 — Complete RAG pipeline runner.

1. Smart chunking with metadata enrichment
2. FAISS Flat + BM25 index building
3. Hybrid retrieval system (75/25 RRF)
4. Golden-query smoke validation
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Optional

from phase2.rag.chunking import SmartChunker
from phase2.rag.config import (
    CHUNK_OVERLAP,
    DEFAULT_TOP_K,
    EMBEDDING_MODEL,
    FAISS_INDEX_TYPE,
    MAX_CHUNK_SIZE,
    MIN_CHUNK_SIZE,
    MIN_FINANCIAL_DENSITY,
)
from phase2.rag.indexing import build_complete_index
from phase2.rag.retrieval import HybridRetriever


def run_phase2_pipeline(
    corpus_run_dir: Path,
    output_dir: Path,
    validation_report_path: Optional[Path] = None,
    chunk_config: Optional[dict[str, Any]] = None,
    index_config: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    print("=" * 60)
    print("Phase 2 — RAG Pipeline")
    print("=" * 60)

    output_dir.mkdir(parents=True, exist_ok=True)

    validation_report = None
    if validation_report_path and validation_report_path.exists():
        with open(validation_report_path, encoding="utf-8") as f:
            validation_report = json.load(f)
        print(f"Loaded validation report: {validation_report_path}")

    cfg = chunk_config or {}
    print("\n1. Smart Chunking")
    print("-" * 30)

    chunker = SmartChunker(
        min_chunk_size=cfg.get("min_size", MIN_CHUNK_SIZE),
        max_chunk_size=cfg.get("max_size", MAX_CHUNK_SIZE),
        overlap=cfg.get("overlap", CHUNK_OVERLAP),
    )

    t0 = time.time()
    chunks = chunker.process_corpus_run(corpus_run_dir, validation_report)
    print(f"Created {len(chunks)} chunks before filtering")

    filtered_chunks = chunker.filter_chunks_by_quality(
        chunks,
        min_financial_density=cfg.get("min_density", MIN_FINANCIAL_DENSITY),
    )
    chunking_time = time.time() - t0
    print(f"Filtered to {len(filtered_chunks)} high-quality chunks ({chunking_time:.2f}s)")

    if not filtered_chunks:
        raise ValueError("No chunks passed quality filtering")

    chunks_output_dir = output_dir / "chunks"
    chunk_result = chunker.save_chunks(filtered_chunks, chunks_output_dir)
    chunks_file = Path(chunk_result["chunks_file"])
    print(f"Chunks saved to: {chunks_file}")

    from phase2.rag.fund_records import build_corpus_fund_registry, save_fund_registry

    fund_records = build_corpus_fund_registry(corpus_run_dir)
    funds_path = save_fund_registry(fund_records, output_dir / "funds" / "fund_records.json")
    print(f"Fund registry saved: {funds_path} ({len(fund_records)} schemes)")

    from phase3.generation.corpus_meta import sync_ui_corpus_meta

    data_as_of = sync_ui_corpus_meta(output_dir)
    if data_as_of:
        print(f"UI corpus date synced: {data_as_of}")

    idx_cfg = index_config or {}
    print("\n2. Index Building")
    print("-" * 30)

    t0 = time.time()
    index_result = build_complete_index(
        chunks_file=chunks_file,
        output_dir=output_dir / "indexes",
        index_type=idx_cfg.get("type", FAISS_INDEX_TYPE),
        embedding_model=idx_cfg.get("model", EMBEDDING_MODEL),
    )
    indexing_time = time.time() - t0
    print(f"Index built in {indexing_time:.2f}s — {index_result['stats']}")

    print("\n3. Hybrid Retrieval Setup")
    print("-" * 30)

    retriever = HybridRetriever(model_name=idx_cfg.get("model", EMBEDDING_MODEL))
    retriever.load_chunks(chunks_file)
    retriever.build_indexes()

    retrieval_dir = output_dir / "retrieval"
    retriever.save_index(retrieval_dir)
    print(f"Retrieval system saved to: {retrieval_dir}")

    print("\n4. Golden Query Validation")
    print("-" * 30)

    test_queries = [
        ("What is the NAV of Choice Mutual Fund?", "Choice Mutual Fund"),
        ("What are the expense ratios for Union Mutual Fund schemes?", "Union Mutual Fund"),
        ("Tell me about SIP minimum for Unifi Liquid Fund", "Unifi Mutual Fund"),
        ("ICICI Prudential mutual fund schemes", "ICICI Prudential Mutual Fund"),
        ("LIC Mutual Fund exit load", "LIC Mutual Fund"),
    ]

    validation_results = []
    for query, expected_amc in test_queries:
        t0 = time.time()
        results = retriever.hybrid_search(query, top_k=DEFAULT_TOP_K)
        elapsed_ms = (time.time() - t0) * 1000

        top_amc = results[0]["amc_name"] if results else None
        amc_match = top_amc == expected_amc if results else False

        validation_results.append(
            {
                "query": query,
                "expected_amc": expected_amc,
                "top_amc": top_amc,
                "amc_routing_ok": amc_match,
                "results_count": len(results),
                "top_score": results[0]["score"] if results else 0.0,
                "search_time_ms": elapsed_ms,
            }
        )
        status = "OK" if amc_match else "MISS"
        print(f"[{status}] {query[:50]}... → {top_amc} ({elapsed_ms:.0f}ms)")

    amc_routing_rate = sum(1 for r in validation_results if r["amc_routing_ok"]) / len(
        validation_results
    )

    pipeline_report = {
        "pipeline_version": "2.1",
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC"),
        "input_corpus": str(corpus_run_dir),
        "output_directory": str(output_dir),
        "strategy": {
            "bm25_weight": retriever.bm25_weight,
            "vector_weight": retriever.vector_weight,
            "use_rrf": retriever.use_rrf,
            "embedding_model": retriever.model_name,
            "index_type": index_result["stats"].get("type", FAISS_INDEX_TYPE),
        },
        "chunking": {
            "total_before_filtering": len(chunks),
            "total_after_filtering": len(filtered_chunks),
            "filter_ratio": len(filtered_chunks) / len(chunks) if chunks else 0,
            "processing_time_seconds": chunking_time,
            "summary": chunk_result["summary"],
        },
        "indexing": {
            "processing_time_seconds": indexing_time,
            "stats": index_result["stats"],
        },
        "validation": {
            "amc_routing_rate": amc_routing_rate,
            "queries": validation_results,
        },
        "files": {
            "chunks_file": str(chunks_file),
            "retrieval_dir": str(retrieval_dir),
            "indexes_dir": str(output_dir / "indexes"),
        },
    }

    report_path = output_dir / "phase2_pipeline_report.json"
    report_path.write_text(json.dumps(pipeline_report, indent=2) + "\n", encoding="utf-8")

    print("\n" + "=" * 60)
    print("Phase 2 Pipeline Completed")
    print("=" * 60)
    print(f"Chunks indexed: {len(filtered_chunks)}")
    print(f"AMC routing accuracy: {amc_routing_rate:.0%}")
    print(f"Report: {report_path}")

    return pipeline_report


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 2 - Complete RAG pipeline")
    parser.add_argument("--corpus-run", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--validation-report", type=Path)
    parser.add_argument("--chunk-min-size", type=int, default=MIN_CHUNK_SIZE)
    parser.add_argument("--chunk-max-size", type=int, default=MAX_CHUNK_SIZE)
    parser.add_argument("--chunk-min-density", type=float, default=MIN_FINANCIAL_DENSITY)
    parser.add_argument("--index-type", type=str, default=FAISS_INDEX_TYPE)
    parser.add_argument("--embedding-model", type=str, default=EMBEDDING_MODEL)
    args = parser.parse_args()

    validation_report = args.validation_report
    if validation_report is None:
        candidate = args.corpus_run / "validation_report.json"
        if candidate.is_file():
            validation_report = candidate

    try:
        run_phase2_pipeline(
            corpus_run_dir=args.corpus_run,
            output_dir=args.output_dir,
            validation_report_path=validation_report,
            chunk_config={
                "min_size": args.chunk_min_size,
                "max_size": args.chunk_max_size,
                "min_density": args.chunk_min_density,
            },
            index_config={"type": args.index_type, "model": args.embedding_model},
        )
        return 0
    except Exception as exc:
        print(f"Pipeline failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
