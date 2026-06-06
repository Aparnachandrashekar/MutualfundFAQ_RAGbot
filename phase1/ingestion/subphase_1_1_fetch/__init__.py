"""Phase 1.1 — fetch layer (allowlist-only HTTP GET)."""

from phase1.ingestion.subphase_1_1_fetch.fetch_layer import (
    DEFAULT_BACKOFF_BASE_SEC,
    DEFAULT_MAX_ATTEMPTS,
    DEFAULT_STAGGER_SEC,
    DEFAULT_TIMEOUT_SEC,
    USER_AGENT,
    FetchAttempt,
    FetchReport,
    build_ssl_context,
    fetch_all_allowlisted,
    fetch_url_allowlisted,
)

__all__ = [
    "DEFAULT_BACKOFF_BASE_SEC",
    "DEFAULT_MAX_ATTEMPTS",
    "DEFAULT_STAGGER_SEC",
    "DEFAULT_TIMEOUT_SEC",
    "USER_AGENT",
    "FetchAttempt",
    "FetchReport",
    "build_ssl_context",
    "fetch_all_allowlisted",
    "fetch_url_allowlisted",
]
