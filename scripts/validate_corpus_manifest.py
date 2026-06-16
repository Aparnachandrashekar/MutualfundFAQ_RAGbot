#!/usr/bin/env python3
"""Validate config/corpus_manifest.json against the six-scheme allowlist."""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = REPO_ROOT / "config" / "corpus_manifest.json"

EXPECTED_URLS = frozenset(
    {
        "https://groww.in/mutual-funds/hdfc-silver-etf-fof-direct-growth",
        "https://groww.in/mutual-funds/hdfc-mid-cap-fund-direct-growth",
        "https://groww.in/mutual-funds/parag-parikh-long-term-value-fund-direct-growth",
        "https://groww.in/mutual-funds/bandhan-small-cap-fund-direct-growth",
        "https://groww.in/mutual-funds/quant-small-cap-fund-direct-plan-growth",
        "https://groww.in/mutual-funds/sbi-gold-fund-direct-growth",
    }
)

EXPECTED_COUNT = 6


def main() -> int:
    if not MANIFEST_PATH.is_file():
        print(f"ERROR: missing {MANIFEST_PATH}", file=sys.stderr)
        return 1

    data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    sources = data.get("sources")
    if not isinstance(sources, list):
        print("ERROR: 'sources' must be a list", file=sys.stderr)
        return 1

    if len(sources) != EXPECTED_COUNT:
        print(f"ERROR: expected exactly {EXPECTED_COUNT} sources, got {len(sources)}", file=sys.stderr)
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
        print("ERROR: URL set must match the six-scheme allowlist exactly.", file=sys.stderr)
        if missing:
            print(f"  Missing: {sorted(missing)}", file=sys.stderr)
        if extra:
            print(f"  Unexpected: {sorted(extra)}", file=sys.stderr)
        return 1

    print(f"OK: corpus_manifest.json matches {EXPECTED_COUNT}-scheme allowlist.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
