#!/usr/bin/env python3
"""Validate config/corpus_manifest.json against Phase 0 rules (stdlib only)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = REPO_ROOT / "config" / "corpus_manifest.json"

# Canonical allowlist from PhaseWiseArchitecture.md — order-independent at validation time.
EXPECTED_URLS = frozenset(
    {
        "https://groww.in/mutual-funds/amc/choice-mutual-funds",
        "https://groww.in/mutual-funds/amc/unifi-mutual-funds",
        "https://groww.in/mutual-funds/amc/union-mutual-funds",
        "https://groww.in/mutual-funds/amc/icici-prudential-mutual-funds",
        "https://groww.in/mutual-funds/amc/lic-mutual-funds",
    }
)


def main() -> int:
    if not MANIFEST_PATH.is_file():
        print(f"ERROR: missing {MANIFEST_PATH}", file=sys.stderr)
        return 1

    data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    sources = data.get("sources")
    if not isinstance(sources, list):
        print("ERROR: 'sources' must be a list", file=sys.stderr)
        return 1

    if len(sources) != 5:
        print(f"ERROR: expected exactly 5 sources, got {len(sources)}", file=sys.stderr)
        return 1

    ids: list[str] = []
    urls: list[str] = []
    for i, src in enumerate(sources):
        if not isinstance(src, dict):
            print(f"ERROR: sources[{i}] must be an object", file=sys.stderr)
            return 1
        sid = src.get("id")
        url = src.get("url")
        if not isinstance(sid, str) or not sid.strip():
            print(f"ERROR: sources[{i}].id must be a non-empty string", file=sys.stderr)
            return 1
        if not isinstance(url, str) or not url.startswith("https://"):
            print(f"ERROR: sources[{i}].url must be an https URL string", file=sys.stderr)
            return 1
        ids.append(sid)
        urls.append(url.strip())

    if len(set(ids)) != len(ids):
        print("ERROR: duplicate source id", file=sys.stderr)
        return 1

    missing = EXPECTED_URLS - set(urls)
    extra = set(urls) - EXPECTED_URLS
    if missing or extra:
        print("ERROR: URL set must match Phase 0 allowlist exactly.", file=sys.stderr)
        if missing:
            print(f"  Missing: {sorted(missing)}", file=sys.stderr)
        if extra:
            print(f"  Unexpected: {sorted(extra)}", file=sys.stderr)
        return 1

    print("OK: corpus_manifest.json matches Phase 0 rules.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
