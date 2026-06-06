"""Load corpus allowlist from config/corpus_manifest.json — only permitted fetch targets."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class AllowlistError(ValueError):
    """Raised when a URL is not in the corpus manifest or manifest is invalid."""


def repo_root() -> Path:
    """Repository root (`phase1/ingestion/common/` → three levels up)."""
    return Path(__file__).resolve().parents[3]


def manifest_path_default() -> Path:
    return repo_root() / "config" / "corpus_manifest.json"


def load_corpus_manifest(path: Path | None = None) -> dict[str, Any]:
    p = path or manifest_path_default()
    if not p.is_file():
        raise FileNotFoundError(f"Corpus manifest not found: {p}")
    return json.loads(p.read_text(encoding="utf-8"))


def load_allowlist(path: Path | None = None) -> frozenset[str]:
    """Return the set of permitted URLs (exact strings from manifest)."""
    data = load_corpus_manifest(path)
    sources = data.get("sources")
    if not isinstance(sources, list):
        raise AllowlistError("manifest 'sources' must be a list")
    urls: list[str] = []
    for i, src in enumerate(sources):
        if not isinstance(src, dict):
            raise AllowlistError(f"sources[{i}] must be an object")
        u = src.get("url")
        if not isinstance(u, str) or not u.startswith("https://"):
            raise AllowlistError(f"sources[{i}].url must be an https URL string")
        urls.append(u.strip())
    return frozenset(urls)


def assert_url_allowlisted(url: str, allowlist: frozenset[str]) -> None:
    if url not in allowlist:
        raise AllowlistError(
            f"URL not in corpus allowlist (runtime fetch rejected): {url!r}. "
            "Only URLs in config/corpus_manifest.json may be fetched."
        )
