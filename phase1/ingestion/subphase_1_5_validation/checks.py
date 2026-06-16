"""Phase 1.5 — structural / automated checks before semantic validation."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from phase1.ingestion.common.allowlist import load_allowlist, load_corpus_manifest, manifest_path_default
from phase1.ingestion.subphase_1_3_html_text.extract import DEFAULT_MIN_CLEAN_TEXT_CHARS, check_min_length
from phase1.ingestion.subphase_1_4_corpus_assembly.assembly import CORPUS_FILENAME, INGEST_MANIFEST_FILENAME

REQUIRED_ARTIFACTS = ("raw.html", "snapshot_meta.json", "clean.txt")


@dataclass
class StructuralCheckResult:
    ok: bool
    errors: list[str] = field(default_factory=list)
    checks: dict[str, bool] = field(default_factory=dict)
    manifest: dict[str, Any] = field(default_factory=dict)
    corpus: dict[str, Any] = field(default_factory=dict)


def _detect_off_allowlist_dirs(run_dir: Path, expected_ids: frozenset[str]) -> list[str]:
    errors: list[str] = []
    for child in run_dir.iterdir():
        if not child.is_dir():
            continue
        if child.name not in expected_ids:
            errors.append(f"off-allowlist source directory: {child.name}")
    return errors


def run_structural_checks(
    run_dir: Path,
    *,
    manifest_path: Path | None = None,
    min_text_chars: int = DEFAULT_MIN_CLEAN_TEXT_CHARS,
) -> StructuralCheckResult:
    """
    Automated checks per PhaseWiseArchitecture.md §1.5:
    - expected sources present (from corpus manifest)
    - Phase 1.4 assembly complete (``corpus.json``)
    - no off-allowlist directories
    - required artifacts and minimum text length per source
    """
    errors: list[str] = []
    checks: dict[str, bool] = {}
    mp = manifest_path or manifest_path_default()
    root_manifest = load_corpus_manifest(mp)
    allowlist = load_allowlist(mp)
    expected_ids = frozenset(str(s["id"]) for s in root_manifest.get("sources", []))
    expected_source_count = len(expected_ids)

    ingest_path = run_dir / INGEST_MANIFEST_FILENAME
    corpus_path = run_dir / CORPUS_FILENAME

    checks["ingest_manifest_present"] = ingest_path.is_file()
    if not checks["ingest_manifest_present"]:
        errors.append("ingest_manifest.json not found")
        return StructuralCheckResult(ok=False, errors=errors, checks=checks)

    ingest_manifest = json.loads(ingest_path.read_text(encoding="utf-8"))
    sources = ingest_manifest.get("sources", [])

    checks["five_sources_present"] = len(sources) == expected_source_count
    if not checks["five_sources_present"]:
        errors.append(f"expected {expected_source_count} sources, got {len(sources)}")

    checks["corpus_json_present"] = corpus_path.is_file()
    corpus: dict[str, Any] = {}
    if checks["corpus_json_present"]:
        corpus = json.loads(corpus_path.read_text(encoding="utf-8"))
    else:
        errors.append("corpus.json not found — run Phase 1.4 assembly first")

    checks["assembly_ok"] = bool(corpus.get("assembly_ok"))
    if corpus and not checks["assembly_ok"]:
        errors.append("corpus.json assembly_ok is false")

    off_allowlist = _detect_off_allowlist_dirs(run_dir, expected_ids)
    checks["no_off_allowlist_dirs"] = len(off_allowlist) == 0
    errors.extend(off_allowlist)

    seen_ids: set[str] = set()
    for source in sources:
        source_id = str(source.get("id", ""))
        seen_ids.add(source_id)
        if source_id not in expected_ids:
            errors.append(f"unknown source id: {source_id!r}")
            continue

        source_dir = run_dir / source_id
        for artifact in REQUIRED_ARTIFACTS:
            if not (source_dir / artifact).is_file():
                errors.append(f"{source_id}: missing {artifact}")

        clean_path = source_dir / "clean.txt"
        if clean_path.is_file():
            text = clean_path.read_text(encoding="utf-8")
            if not check_min_length(text, minimum=min_text_chars):
                errors.append(
                    f"{source_id}: clean.txt too short ({len(text)} < {min_text_chars})"
                )

        canonical = str(source.get("canonical_url", ""))
        if canonical and canonical not in allowlist:
            errors.append(f"{source_id}: canonical_url not in allowlist")

    for missing in sorted(expected_ids - seen_ids):
        errors.append(f"missing source in ingest manifest: {missing}")

    checks["all_artifacts_present"] = not any("missing" in e for e in errors)
    checks["min_text_length_ok"] = not any("too short" in e for e in errors)

    ok = len(errors) == 0 and all(
        checks.get(key, False)
        for key in (
            "ingest_manifest_present",
            "five_sources_present",
            "corpus_json_present",
            "assembly_ok",
            "no_off_allowlist_dirs",
        )
    )
    return StructuralCheckResult(
        ok=ok,
        errors=errors,
        checks=checks,
        manifest=ingest_manifest,
        corpus=corpus,
    )
