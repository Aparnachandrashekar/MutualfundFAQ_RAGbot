"""Corpus as-of date helpers shared by the API, pipeline, and UI."""

from __future__ import annotations

import json
from pathlib import Path

UI_CORPUS_META_PATH = (
    Path(__file__).resolve().parents[2] / "phase4" / "ui" / "data" / "corpus-meta.json"
)


def read_corpus_data_as_of(phase2_dir: Path) -> str | None:
    """Return YYYY-MM-DD for the indexed corpus snapshot."""
    registry_path = phase2_dir / "funds" / "fund_records.json"
    if registry_path.is_file():
        try:
            data = json.loads(registry_path.read_text(encoding="utf-8"))
            dates = [
                fund.get("ingested_at", "").split("T")[0]
                for fund in data.get("funds", [])
                if fund.get("ingested_at")
            ]
            if dates:
                return max(dates)
        except (json.JSONDecodeError, OSError):
            pass

    report_path = phase2_dir / "phase2_pipeline_report.json"
    if report_path.is_file():
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
            timestamp = report.get("timestamp", "")
            if timestamp:
                return timestamp.split()[0]
        except (json.JSONDecodeError, OSError):
            pass

    return None


def sync_ui_corpus_meta(phase2_dir: Path) -> str | None:
    """Write the corpus as-of date for the static UI footer."""
    data_as_of = read_corpus_data_as_of(phase2_dir)
    if not data_as_of:
        return None

    UI_CORPUS_META_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {"data_as_of": data_as_of}
    UI_CORPUS_META_PATH.write_text(
        json.dumps(payload, indent=2) + "\n",
        encoding="utf-8",
    )
    return data_as_of
