"""Phase 1.2 — persist immutable raw response bytes + snapshot metadata per source per run."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from phase1.ingestion.subphase_1_1_fetch.fetch_layer import FetchReport


def new_run_id() -> str:
    """UTC timestamp safe for directory names (microseconds reduce collision risk)."""
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")


RAW_FILENAME = "raw.html"
META_FILENAME = "snapshot_meta.json"


@dataclass
class StoredSnapshotPaths:
    source_dir: Path
    raw_html: Path
    snapshot_meta: Path


def stored_snapshot_relative(source_id: str) -> dict[str, str]:
    return {
        "raw_html_path": f"{source_id}/{RAW_FILENAME}",
        "snapshot_meta_path": f"{source_id}/{META_FILENAME}",
    }


def write_raw_snapshot(
    run_dir: Path,
    report: FetchReport,
    *,
    fetched_at_utc: str,
) -> StoredSnapshotPaths:
    """
    Write ``report.raw_body`` as ``raw.html`` plus ``snapshot_meta.json``.

    Requires ``report.ok`` and non-empty ``report.raw_body``.
    """
    if not report.ok or not report.raw_body:
        raise ValueError("write_raw_snapshot requires a successful report with raw_body set")

    source_dir = run_dir / report.source_id
    source_dir.mkdir(parents=True, exist_ok=True)
    raw_path = source_dir / RAW_FILENAME
    meta_path = source_dir / META_FILENAME

    raw_path.write_bytes(report.raw_body)

    meta: dict[str, Any] = {
        "source_id": report.source_id,
        "amc_name": report.amc_name,
        "canonical_url": report.url,
        "fetched_at_utc": fetched_at_utc,
        "status_code": report.status_code,
        "final_url": report.final_url,
        "content_type": report.content_type,
        "content_type_header": report.content_type_header,
        "body_bytes": report.body_bytes,
    }
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    return StoredSnapshotPaths(
        source_dir=source_dir,
        raw_html=raw_path,
        snapshot_meta=meta_path,
    )
