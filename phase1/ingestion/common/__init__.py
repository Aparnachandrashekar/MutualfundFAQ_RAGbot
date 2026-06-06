"""Shared ingestion utilities (manifest, allowlist — used by all Phase 1 sub-phases)."""

from phase1.ingestion.common.allowlist import (
    AllowlistError,
    assert_url_allowlisted,
    load_allowlist,
    load_corpus_manifest,
    manifest_path_default,
    repo_root,
)
from phase1.ingestion.common.paths import corpus_runs_dir, latest_corpus_run_dir

__all__ = [
    "AllowlistError",
    "assert_url_allowlisted",
    "corpus_runs_dir",
    "latest_corpus_run_dir",
    "load_allowlist",
    "load_corpus_manifest",
    "manifest_path_default",
    "repo_root",
]
