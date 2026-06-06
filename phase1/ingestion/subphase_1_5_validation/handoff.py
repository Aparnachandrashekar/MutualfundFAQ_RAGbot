"""Phase 1.5 — handoff checklist for Phase 2."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

HANDOFF_FILENAME = "handoff_checklist.json"


def build_handoff_checklist(
    run_dir: Path,
    *,
    structural_checks: dict[str, bool],
    validation_ok: bool,
    validation_report_path: Path,
    embedding_quality_path: Path,
) -> dict[str, Any]:
    """Build formal Phase 1 → Phase 2 handoff checklist."""
    checklist_items = [
        {"name": "five_sources_present", "passed": structural_checks.get("five_sources_present", False)},
        {"name": "corpus_assembly_ok", "passed": structural_checks.get("assembly_ok", False)},
        {"name": "no_off_allowlist_dirs", "passed": structural_checks.get("no_off_allowlist_dirs", False)},
        {"name": "all_artifacts_present", "passed": structural_checks.get("all_artifacts_present", False)},
        {"name": "min_text_length_ok", "passed": structural_checks.get("min_text_length_ok", False)},
        {"name": "semantic_validation_passed", "passed": validation_ok},
    ]

    phase_1_complete = validation_ok and all(item["passed"] for item in checklist_items[:-1])

    return {
        "phase_1_complete": phase_1_complete,
        "validated_at_utc": datetime.now(timezone.utc).isoformat(),
        "checks": checklist_items,
        "handoff_to_phase_2": {
            "corpus_run_dir": str(run_dir.resolve()),
            "corpus_json": str((run_dir / "corpus.json").resolve()),
            "ingest_manifest": str((run_dir / "ingest_manifest.json").resolve()),
            "validation_report": str(validation_report_path.resolve()),
            "embedding_quality": str(embedding_quality_path.resolve()),
        },
    }


def write_handoff_checklist(run_dir: Path, checklist: dict[str, Any]) -> Path:
    path = run_dir / HANDOFF_FILENAME
    path.write_text(json.dumps(checklist, indent=2) + "\n", encoding="utf-8")
    return path
