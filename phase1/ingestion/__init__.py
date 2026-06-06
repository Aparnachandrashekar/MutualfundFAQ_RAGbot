"""Ingestion pipeline — Phase 1 sub-phases under `subphase_*` packages."""

from phase1.ingestion.common.allowlist import (
    AllowlistError,
    load_allowlist,
    load_corpus_manifest,
    manifest_path_default,
)
from phase1.ingestion.subphase_1_1_fetch.fetch_layer import (
    DEFAULT_STAGGER_SEC,
    DEFAULT_TIMEOUT_SEC,
    USER_AGENT,
    FetchReport,
    fetch_all_allowlisted,
    fetch_url_allowlisted,
)

__all__ = [
    "AllowlistError",
    "DEFAULT_STAGGER_SEC",
    "DEFAULT_TIMEOUT_SEC",
    "FetchReport",
    "USER_AGENT",
    "fetch_all_allowlisted",
    "fetch_url_allowlisted",
    "load_allowlist",
    "load_corpus_manifest",
    "manifest_path_default",
]
