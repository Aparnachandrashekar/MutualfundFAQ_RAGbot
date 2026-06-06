"""Filesystem locations for ingestion outputs."""

from __future__ import annotations

from pathlib import Path

from phase1.ingestion.common.allowlist import repo_root


def corpus_runs_dir() -> Path:
    """Root directory for timestamped ingest runs (raw + clean text)."""
    return repo_root() / "data" / "corpus_runs"


def latest_corpus_run_dir(runs_root: Path | None = None) -> Path | None:
    """Return the lexicographically latest run directory under ``corpus_runs/``."""
    root = runs_root or corpus_runs_dir()
    if not root.is_dir():
        return None
    candidates = [d for d in root.iterdir() if d.is_dir() and d.name[:1].isdigit()]
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.name)
