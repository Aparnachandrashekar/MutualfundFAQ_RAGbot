#!/usr/bin/env python3
"""
Phase 1.5 — Validation, monitoring, and handoff checklist using bge-small-en embeddings.

Per PhaseWiseArchitecture.md §1.5:
- Semantic validation with bge-small-en chunk embeddings
- Navigation/footer contamination detection via similarity analysis
- Mutual fund content validation (NAV, schemes, performance terms)
- Embedding quality scores for Phase 2 chunking preparation
- Structural checks, validation report, and handoff checklist
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

from phase1.ingestion.common.paths import corpus_runs_dir, latest_corpus_run_dir
from phase1.ingestion.subphase_1_3_html_text.extract import DEFAULT_MIN_CLEAN_TEXT_CHARS
from phase1.ingestion.subphase_1_4_corpus_assembly.assembly import INGEST_MANIFEST_FILENAME
from phase1.ingestion.subphase_1_5_validation.checks import run_structural_checks
from phase1.ingestion.subphase_1_5_validation.handoff import build_handoff_checklist, write_handoff_checklist

# bge-small-en per architecture (Phase 1.5 + Phase 2 vector search)
MODEL_NAME = "BAAI/bge-small-en-v1.5"
VALIDATION_CHUNK_SIZE = 512

FINANCIAL_KEYWORDS = [
    "mutual fund", "NAV", "net asset value", "scheme", "performance", "returns",
    "expense ratio", "exit load", "SIP", "systematic investment plan", "lump sum",
    "fund manager", "AUM", "assets under management", "risk", "portfolio", "equity",
    "debt", "hybrid", "index fund", "ELSS", "tax saving", "dividend", "growth",
    "fund size", "minimum investment", "direct plan", "regular plan",
]

NAVIGATION_KEYWORDS = [
    "invest in stocks", "IPO", "demat account", "trading", "futures", "options",
    "commodities", "API trading", "terminal", "watchlist", "screener", "chart",
    "brokerage", "intraday", "margin trading", "commodities trading",
]

MIN_CONTENT_QUALITY_SCORE = 0.05
MIN_FINANCIAL_RELEVANCE = 0.55
MAX_NAVIGATION_CONTAMINATION = 0.72
MIN_SEMANTIC_COHERENCE = 0.75
MIN_EMBEDDING_QUALITY = 0.05

VALIDATION_REPORT_FILENAME = "validation_report.json"
EMBEDDING_QUALITY_FILENAME = "embedding_quality.json"


@dataclass
class ValidationRunResult:
    ok: bool
    run_dir: Path
    report: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


class SemanticValidator:
    """Semantic validation using bge-small-en embeddings."""

    def __init__(self, model_name: str = MODEL_NAME):
        self.model_name = model_name
        self.model = SentenceTransformer(model_name)
        self.financial_embeddings = self._encode_reference(FINANCIAL_KEYWORDS)
        self.navigation_embeddings = self._encode_reference(NAVIGATION_KEYWORDS)

    def _encode_reference(self, texts: list[str]) -> np.ndarray:
        return self.model.encode(texts, normalize_embeddings=True)

    def split_validation_chunks(self, text: str, chunk_size: int = VALIDATION_CHUNK_SIZE) -> list[str]:
        """Sentence-accumulation chunks for validation embedding (not Phase 2 retrieval chunks)."""
        sentences = [s.strip() for s in text.split(".") if s.strip()]
        chunks: list[str] = []
        current = ""

        for sentence in sentences:
            candidate = f"{current}{sentence}. "
            if len(candidate) <= chunk_size:
                current = candidate
            else:
                if current.strip():
                    chunks.append(current.strip())
                current = f"{sentence}. "

        if current.strip():
            chunks.append(current.strip())

        return chunks

    def embed_chunks(self, chunks: list[str]) -> np.ndarray:
        if not chunks:
            return np.array([])
        return self.model.encode(chunks, normalize_embeddings=True)

    def calculate_financial_relevance(self, embeddings: np.ndarray) -> float:
        if len(embeddings) == 0:
            return 0.0
        similarities = cosine_similarity(embeddings, self.financial_embeddings)
        return float(np.max(similarities))

    def calculate_navigation_contamination(self, embeddings: np.ndarray) -> float:
        if len(embeddings) == 0:
            return 0.0
        similarities = cosine_similarity(embeddings, self.navigation_embeddings)
        return float(np.max(similarities))

    def calculate_semantic_coherence(self, embeddings: np.ndarray) -> float:
        """Mean cosine similarity of each chunk to the corpus centroid."""
        if len(embeddings) == 0:
            return 0.0
        if len(embeddings) == 1:
            return 1.0
        centroid = np.mean(embeddings, axis=0, keepdims=True)
        similarities = cosine_similarity(embeddings, centroid)
        return float(np.mean(similarities))

    def per_chunk_scores(self, chunks: list[str], embeddings: np.ndarray) -> list[dict[str, float]]:
        scores: list[dict[str, float]] = []
        for idx, _chunk in enumerate(chunks):
            row = embeddings[idx : idx + 1]
            fin = float(np.max(cosine_similarity(row, self.financial_embeddings)))
            nav = float(np.max(cosine_similarity(row, self.navigation_embeddings)))
            quality = max(0.0, fin - nav)
            scores.append(
                {
                    "chunk_index": idx,
                    "financial_relevance": round(fin, 4),
                    "navigation_contamination": round(nav, 4),
                    "embedding_quality": round(quality, 4),
                }
            )
        return scores

    def calculate_content_quality_score(self, text: str) -> dict[str, Any]:
        chunks = self.split_validation_chunks(text)
        embeddings = self.embed_chunks(chunks)

        if len(embeddings) == 0:
            return {
                "financial_relevance": 0.0,
                "navigation_contamination": 0.0,
                "content_quality": 0.0,
                "semantic_coherence": 0.0,
                "embedding_quality": 0.0,
                "chunk_count": 0,
                "chunk_scores": [],
            }

        chunk_scores = self.per_chunk_scores(chunks, embeddings)
        financial_relevance = float(np.mean([s["financial_relevance"] for s in chunk_scores]))
        navigation_contamination = float(np.mean([s["navigation_contamination"] for s in chunk_scores]))
        embedding_quality = float(np.mean([s["embedding_quality"] for s in chunk_scores]))
        content_quality = embedding_quality
        semantic_coherence = self.calculate_semantic_coherence(embeddings)

        return {
            "financial_relevance": round(financial_relevance, 4),
            "navigation_contamination": round(navigation_contamination, 4),
            "content_quality": round(content_quality, 4),
            "semantic_coherence": round(semantic_coherence, 4),
            "embedding_quality": round(embedding_quality, 4),
            "chunk_count": len(chunks),
            "chunk_scores": chunk_scores,
        }

    def validate_source(self, source_path: Path, *, min_text_chars: int) -> dict[str, Any]:
        clean_text_path = source_path / "clean.txt"
        if not clean_text_path.is_file():
            return {"validation_ok": False, "error": "clean.txt not found", "metrics": {}}

        text = clean_text_path.read_text(encoding="utf-8")
        if len(text) < min_text_chars:
            return {
                "validation_ok": False,
                "error": f"Text too short: {len(text)} chars",
                "metrics": {"text_length": len(text)},
            }

        metrics = self.calculate_content_quality_score(text)
        metrics["text_length"] = len(text)

        validation_ok = (
            metrics["content_quality"] >= MIN_CONTENT_QUALITY_SCORE
            and metrics["financial_relevance"] >= MIN_FINANCIAL_RELEVANCE
            and metrics["navigation_contamination"] <= MAX_NAVIGATION_CONTAMINATION
            and metrics["semantic_coherence"] >= MIN_SEMANTIC_COHERENCE
            and metrics["embedding_quality"] >= MIN_EMBEDDING_QUALITY
        )

        return {
            "validation_ok": validation_ok,
            "error": None if validation_ok else "Content quality below thresholds",
            "metrics": metrics,
        }


def validate_run(
    run_dir: Path,
    *,
    validator: SemanticValidator | None = None,
    min_text_chars: int = DEFAULT_MIN_CLEAN_TEXT_CHARS,
    manifest_path: Path | None = None,
) -> ValidationRunResult:
    """Run full Phase 1.5 validation pipeline on an assembled corpus run."""
    errors: list[str] = []
    validated_at = datetime.now(timezone.utc).isoformat()

    structural = run_structural_checks(run_dir, manifest_path=manifest_path, min_text_chars=min_text_chars)
    if not structural.ok:
        report = {
            "validation_ok": False,
            "validated_at_utc": validated_at,
            "error": "Structural checks failed",
            "structural_checks": structural.checks,
            "structural_errors": structural.errors,
            "sources": {},
            "summary": {
                "total_sources": 0,
                "passed_sources": 0,
                "total_characters": 0,
                "avg_content_quality": 0.0,
                "avg_semantic_coherence": 0.0,
                "avg_embedding_quality": 0.0,
                "model_used": MODEL_NAME,
            },
        }
        _write_outputs(run_dir, report, {}, structural.checks, False)
        return ValidationRunResult(ok=False, run_dir=run_dir, report=report, errors=structural.errors)

    semantic = validator or SemanticValidator()
    validation_results: dict[str, Any] = {}
    embedding_quality_sources: dict[str, Any] = {}
    overall_ok = True

    for source in structural.manifest.get("sources", []):
        source_id = str(source["id"])
        result = semantic.validate_source(run_dir / source_id, min_text_chars=min_text_chars)
        validation_results[source_id] = {
            "validation_ok": result["validation_ok"],
            "error": result["error"],
            "metrics": {
                k: v for k, v in result.get("metrics", {}).items() if k != "chunk_scores"
            },
        }
        if not result["validation_ok"]:
            overall_ok = False
            if result.get("error"):
                errors.append(f"{source_id}: {result['error']}")

        metrics = result.get("metrics", {})
        embedding_quality_sources[source_id] = {
            "content_quality": metrics.get("content_quality", 0.0),
            "semantic_coherence": metrics.get("semantic_coherence", 0.0),
            "embedding_quality": metrics.get("embedding_quality", 0.0),
            "chunk_scores": metrics.get("chunk_scores", []),
        }

    total_chars = sum(
        r.get("metrics", {}).get("text_length", 0) for r in validation_results.values()
    )
    content_qualities = [
        r["metrics"]["content_quality"]
        for r in validation_results.values()
        if r.get("metrics") and "content_quality" in r["metrics"]
    ]
    coherences = [
        r["metrics"]["semantic_coherence"]
        for r in validation_results.values()
        if r.get("metrics") and "semantic_coherence" in r["metrics"]
    ]
    embed_qualities = [
        r["metrics"]["embedding_quality"]
        for r in validation_results.values()
        if r.get("metrics") and "embedding_quality" in r["metrics"]
    ]

    report = {
        "validation_ok": overall_ok,
        "validated_at_utc": validated_at,
        "error": None if overall_ok else "One or more sources failed validation",
        "structural_checks": structural.checks,
        "sources": validation_results,
        "summary": {
            "total_sources": len(structural.manifest.get("sources", [])),
            "passed_sources": sum(1 for r in validation_results.values() if r["validation_ok"]),
            "total_characters": total_chars,
            "avg_content_quality": float(np.mean(content_qualities)) if content_qualities else 0.0,
            "avg_semantic_coherence": float(np.mean(coherences)) if coherences else 0.0,
            "avg_embedding_quality": float(np.mean(embed_qualities)) if embed_qualities else 0.0,
            "model_used": semantic.model_name,
            "validation_chunk_size": VALIDATION_CHUNK_SIZE,
            "thresholds": {
                "min_content_quality": MIN_CONTENT_QUALITY_SCORE,
                "min_financial_relevance": MIN_FINANCIAL_RELEVANCE,
                "max_navigation_contamination": MAX_NAVIGATION_CONTAMINATION,
                "min_semantic_coherence": MIN_SEMANTIC_COHERENCE,
                "min_embedding_quality": MIN_EMBEDDING_QUALITY,
                "min_text_chars": min_text_chars,
            },
        },
    }

    embedding_quality = {
        "run_id": structural.manifest.get("run_id"),
        "validated_at_utc": validated_at,
        "model": semantic.model_name,
        "validation_chunk_size": VALIDATION_CHUNK_SIZE,
        "sources": embedding_quality_sources,
    }

    _write_outputs(run_dir, report, embedding_quality, structural.checks, overall_ok)
    _update_ingest_manifest(run_dir, overall_ok)

    return ValidationRunResult(ok=overall_ok, run_dir=run_dir, report=report, errors=errors)


def _write_outputs(
    run_dir: Path,
    report: dict[str, Any],
    embedding_quality: dict[str, Any],
    structural_checks: dict[str, bool],
    validation_ok: bool,
) -> None:
    validation_path = run_dir / VALIDATION_REPORT_FILENAME
    embedding_path = run_dir / EMBEDDING_QUALITY_FILENAME

    validation_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    embedding_path.write_text(json.dumps(embedding_quality, indent=2) + "\n", encoding="utf-8")

    checklist = build_handoff_checklist(
        run_dir,
        structural_checks=structural_checks,
        validation_ok=validation_ok,
        validation_report_path=validation_path,
        embedding_quality_path=embedding_path,
    )
    write_handoff_checklist(run_dir, checklist)


def _update_ingest_manifest(run_dir: Path, validation_ok: bool) -> None:
    manifest_path = run_dir / INGEST_MANIFEST_FILENAME
    if not manifest_path.is_file():
        return
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    phases = list(manifest.get("phases", []))
    if "1.5" not in phases:
        phases.append("1.5")
    manifest["phases"] = phases
    manifest["validated_at_utc"] = datetime.now(timezone.utc).isoformat()
    manifest["validation_ok"] = validation_ok
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Phase 1.5 semantic validation")
    parser.add_argument("--run-dir", type=Path, help="Specific run directory to validate")
    parser.add_argument("--runs-dir", type=Path, default=None, help="Default: data/corpus_runs")
    parser.add_argument("--manifest", type=Path, default=None)
    parser.add_argument("--min-text-chars", type=int, default=DEFAULT_MIN_CLEAN_TEXT_CHARS)
    parser.add_argument("--output", type=Path, help="Override validation report output path")
    args = parser.parse_args()

    runs_root = args.runs_dir or corpus_runs_dir()
    if args.run_dir:
        run_dir = args.run_dir
    else:
        run_dir = latest_corpus_run_dir(runs_root)
        if run_dir is None:
            print(f"No run directories found under {runs_root}", file=sys.stderr)
            return 1

    print(f"Validating run: {run_dir.resolve()}")
    print(f"Model:        {MODEL_NAME}")
    print()

    validator = SemanticValidator()
    result = validate_run(
        run_dir,
        validator=validator,
        min_text_chars=args.min_text_chars,
        manifest_path=args.manifest,
    )

    if args.output:
        args.output.write_text(json.dumps(result.report, indent=2) + "\n", encoding="utf-8")

    summary = result.report.get("summary", {})
    for source_id, source_result in result.report.get("sources", {}).items():
        metrics = source_result.get("metrics", {})
        flag = "OK" if source_result.get("validation_ok") else "FAIL"
        print(
            f"[{flag}] {source_id} quality={metrics.get('content_quality', 0):.3f} "
            f"coherence={metrics.get('semantic_coherence', 0):.3f} "
            f"embed={metrics.get('embedding_quality', 0):.3f}"
        )

    print()
    print(f"Wrote {run_dir / VALIDATION_REPORT_FILENAME}")
    print(f"Wrote {run_dir / EMBEDDING_QUALITY_FILENAME}")
    print(f"Wrote {run_dir / 'handoff_checklist.json'}")

    if result.ok:
        print("Phase 1.5 validation passed.")
        print(
            f"Summary: {summary.get('passed_sources')}/{summary.get('total_sources')} sources, "
            f"avg quality={summary.get('avg_content_quality', 0):.3f}"
        )
        return 0

    print("Phase 1.5 validation failed.", file=sys.stderr)
    if result.report.get("structural_errors"):
        for err in result.report["structural_errors"]:
            print(f"  structural: {err}", file=sys.stderr)
    for err in result.errors:
        print(f"  {err}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
