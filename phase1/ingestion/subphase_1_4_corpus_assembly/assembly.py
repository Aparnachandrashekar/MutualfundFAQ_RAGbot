"""Phase 1.4 — corpus assembly and manifest metadata."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from phase1.ingestion.common.allowlist import load_allowlist, load_corpus_manifest, manifest_path_default
from phase1.ingestion.subphase_1_3_html_text.extract import DEFAULT_MIN_CLEAN_TEXT_CHARS, check_min_length

INGEST_MANIFEST_FILENAME = "ingest_manifest.json"
CORPUS_FILENAME = "corpus.json"

REQUIRED_ARTIFACTS = ("raw.html", "snapshot_meta.json", "clean.txt")

TABLE_HEADER_LINES = frozenset(
    {
        "Fund Name",
        "Category",
        "Risk",
        "NAV",
        "Expense Ratio",
        "1Y Returns",
        "3Y Returns",
        "5Y Returns",
        "7Y Returns",
        "10Y Returns",
        "Rating",
        "Fund Size (in Cr)",
        "Exit Load",
        "View All",
        "Returns calculator",
        "Select a Fund",
        "Invest Now",
        "No Data Available",
        "Key information",
        "Mutual fund name",
        "Asset management company name",
    }
)

SCHEME_NAME_RE = re.compile(
    r"^[A-Z][\w\s&\-]+(?:Fund|ETF)(?:\s+Direct\s+(?:Growth|IDCW|Payout|Bonus))?$"
)


@dataclass
class AssemblyResult:
    ok: bool
    run_dir: Path
    errors: list[str] = field(default_factory=list)
    corpus: dict[str, Any] = field(default_factory=dict)


def amc_prefix(amc_name: str) -> str:
    return amc_name.replace(" Mutual Fund", "").strip()


def extract_scheme_names(text: str, amc_name: str) -> list[str]:
    """
    Best-effort scheme name extraction from Groww AMC overview clean text.

    Looks for fund names in the scheme listing section; optional metadata for Phase 2 routing.
    """
    prefix = amc_prefix(amc_name)
    start_idx = 0
    for marker in (f"List of {amc_name}", f"List of {prefix}"):
        idx = text.find(marker)
        if idx >= 0:
            start_idx = idx
            break

    section = text[start_idx : start_idx + 10_000] if start_idx else text
    schemes: list[str] = []
    seen: set[str] = set()

    for line in section.splitlines():
        line = line.strip()
        if not line or line in TABLE_HEADER_LINES:
            continue
        if len(line) < 8 or len(line) > 80:
            continue
        if line == amc_name or line.startswith(("List of ", "about ", "The ", "Lump sum ")):
            continue
        if any(token in line for token in (" comes under ", " is ₹", " for SIP", "Private Ltd", "Private Limited")):
            continue
        if line.endswith(" Mutual Fund") and prefix not in line:
            continue
        if not SCHEME_NAME_RE.match(line):
            continue
        if prefix.lower() not in line.lower():
            continue
        if line not in seen:
            seen.add(line)
            schemes.append(line)

    return sorted(schemes)


def _load_snapshot_meta(source_dir: Path) -> dict[str, Any]:
    meta_path = source_dir / "snapshot_meta.json"
    if not meta_path.is_file():
        raise FileNotFoundError(f"missing {meta_path.name}")
    return json.loads(meta_path.read_text(encoding="utf-8"))


def _validate_source_artifacts(
    run_dir: Path,
    source: dict[str, Any],
    allowlist: frozenset[str],
    min_text_chars: int,
) -> tuple[dict[str, Any] | None, list[str]]:
    """Validate one source directory; return enriched record or None with errors."""
    errors: list[str] = []
    source_id = str(source.get("id", ""))
    source_dir = run_dir / source_id

    if not source_dir.is_dir():
        return None, [f"{source_id}: source directory missing"]

    for artifact in REQUIRED_ARTIFACTS:
        if not (source_dir / artifact).is_file():
            errors.append(f"{source_id}: missing {artifact}")

    if errors:
        return None, errors

    snapshot_meta = _load_snapshot_meta(source_dir)
    canonical_url = str(snapshot_meta.get("canonical_url", ""))
    if canonical_url not in allowlist:
        errors.append(f"{source_id}: canonical_url not in allowlist: {canonical_url!r}")

    clean_path = source_dir / "clean.txt"
    clean_text = clean_path.read_text(encoding="utf-8")
    clean_chars = len(clean_text)
    if not check_min_length(clean_text, minimum=min_text_chars):
        errors.append(f"{source_id}: clean.txt too short ({clean_chars} < {min_text_chars})")

    if errors:
        return None, errors

    fetched_at = snapshot_meta.get("fetched_at_utc") or source.get("fetched_at_utc")
    scheme_names = extract_scheme_names(clean_text, str(source.get("amc_name", "")))

    enriched: dict[str, Any] = {
        **source,
        "id": source_id,
        "amc_name": source.get("amc_name"),
        "canonical_url": source.get("canonical_url") or canonical_url,
        "source_url": canonical_url,
        "fetched_at_utc": fetched_at,
        "raw_html_path": f"{source_id}/raw.html",
        "snapshot_meta_path": f"{source_id}/snapshot_meta.json",
        "clean_text_path": f"{source_id}/clean.txt",
        "clean_text_chars": clean_chars,
        "scheme_names_observed": scheme_names,
        "fetch_ok": bool(source.get("fetch_ok", True)),
        "extraction_ok": bool(source.get("extraction_ok", True)),
        "assembly_ok": True,
    }
    return enriched, []


def _detect_off_allowlist_dirs(run_dir: Path, expected_ids: frozenset[str]) -> list[str]:
    errors: list[str] = []
    for child in run_dir.iterdir():
        if not child.is_dir():
            continue
        if child.name not in expected_ids:
            errors.append(f"off-allowlist source directory: {child.name}")
    return errors


def assemble_corpus(
    run_dir: Path,
    *,
    manifest_path: Path | None = None,
    min_text_chars: int = DEFAULT_MIN_CLEAN_TEXT_CHARS,
    update_root_manifest: bool = True,
) -> AssemblyResult:
    """
    Assemble a complete corpus run for Phase 2 handoff.

    - Validates all five allowlisted sources and required artifacts
    - Enriches ``ingest_manifest.json`` with ``fetched_at_utc`` and scheme names
    - Writes ``corpus.json`` as the single build output for Phase 2
    - Optionally updates ``config/corpus_manifest.json`` ``last_fetch_at`` / scheme names
    """
    errors: list[str] = []
    mp = manifest_path or manifest_path_default()
    allowlist = load_allowlist(mp)
    root_manifest = load_corpus_manifest(mp)
    expected_ids = frozenset(str(s["id"]) for s in root_manifest.get("sources", []))

    ingest_path = run_dir / INGEST_MANIFEST_FILENAME
    if not ingest_path.is_file():
        return AssemblyResult(ok=False, run_dir=run_dir, errors=["ingest_manifest.json not found"])

    ingest_manifest = json.loads(ingest_path.read_text(encoding="utf-8"))
    ingest_sources = ingest_manifest.get("sources", [])
    if len(ingest_sources) != 5:
        errors.append(f"expected 5 sources in ingest manifest, got {len(ingest_sources)}")

    errors.extend(_detect_off_allowlist_dirs(run_dir, expected_ids))

    enriched_sources: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    for source in ingest_sources:
        source_id = str(source.get("id", ""))
        if source_id not in expected_ids:
            errors.append(f"unknown source id in ingest manifest: {source_id!r}")
            continue
        seen_ids.add(source_id)
        enriched, source_errors = _validate_source_artifacts(
            run_dir, source, allowlist, min_text_chars
        )
        if source_errors:
            errors.extend(source_errors)
            enriched_sources.append({**source, "assembly_ok": False})
        elif enriched:
            enriched_sources.append(enriched)

    missing_ids = expected_ids - seen_ids
    for missing in sorted(missing_ids):
        errors.append(f"missing source in ingest manifest: {missing}")

    assembled_at = datetime.now(timezone.utc).isoformat()
    assembly_ok = len(errors) == 0 and len(enriched_sources) == 5 and all(
        s.get("assembly_ok") for s in enriched_sources
    )

    phases = list(ingest_manifest.get("phases", ["1.1", "1.2", "1.3"]))
    if "1.4" not in phases:
        phases.append("1.4")

    ingest_manifest.update(
        {
            "phases": phases,
            "assembled_at_utc": assembled_at,
            "assembly_ok": assembly_ok,
            "min_clean_text_chars": min_text_chars,
            "sources": enriched_sources,
        }
    )
    ingest_path.write_text(json.dumps(ingest_manifest, indent=2) + "\n", encoding="utf-8")

    documents = [
        {
            "id": s["id"],
            "amc_name": s["amc_name"],
            "source_url": s["source_url"],
            "canonical_url": s["canonical_url"],
            "fetched_at_utc": s["fetched_at_utc"],
            "clean_text_path": s["clean_text_path"],
            "clean_text_chars": s["clean_text_chars"],
            "scheme_names_observed": s["scheme_names_observed"],
            "assembly_ok": s.get("assembly_ok", False),
        }
        for s in enriched_sources
    ]

    corpus: dict[str, Any] = {
        "run_id": ingest_manifest.get("run_id"),
        "created_at_utc": ingest_manifest.get("created_at_utc"),
        "assembled_at_utc": assembled_at,
        "assembly_ok": assembly_ok,
        "source_count": len(documents),
        "manifest_path": str(mp.resolve()),
        "documents": documents,
    }
    (run_dir / CORPUS_FILENAME).write_text(json.dumps(corpus, indent=2) + "\n", encoding="utf-8")

    if update_root_manifest and assembly_ok:
        _update_root_corpus_manifest(mp, enriched_sources)

    return AssemblyResult(ok=assembly_ok, run_dir=run_dir, errors=errors, corpus=corpus)


def _update_root_corpus_manifest(
    root_manifest_path: Path,
    assembled_sources: list[dict[str, Any]],
) -> None:
    data = json.loads(root_manifest_path.read_text(encoding="utf-8"))
    by_id = {str(s["id"]): s for s in assembled_sources}
    for src in data.get("sources", []):
        sid = str(src.get("id", ""))
        if sid not in by_id:
            continue
        assembled = by_id[sid]
        src["last_fetch_at"] = assembled.get("fetched_at_utc")
        src["scheme_names_observed"] = assembled.get("scheme_names_observed", [])
    root_manifest_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
