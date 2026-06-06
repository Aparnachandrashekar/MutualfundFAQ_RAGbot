#!/usr/bin/env python3
"""
Phase 1.1 CLI: fetch all allowlisted URLs and print a per-URL report.

Run from repository root:
  python3 -m phase1.ingestion.subphase_1_1_fetch.run

Exit code 0 if all fetches return HTTP 2xx; otherwise 1 (no silent failures).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from phase1.ingestion.common.allowlist import manifest_path_default
from phase1.ingestion.subphase_1_1_fetch.fetch_layer import (
    DEFAULT_BACKOFF_BASE_SEC,
    DEFAULT_MAX_ATTEMPTS,
    DEFAULT_STAGGER_SEC,
    DEFAULT_TIMEOUT_SEC,
    USER_AGENT,
    fetch_all_allowlisted,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 1.1 — allowlist fetch run")
    parser.add_argument(
        "--manifest",
        type=Path,
        default=None,
        help="Path to corpus_manifest.json (default: config/corpus_manifest.json)",
    )
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_SEC)
    parser.add_argument("--stagger", type=float, default=DEFAULT_STAGGER_SEC)
    parser.add_argument("--max-attempts", type=int, default=DEFAULT_MAX_ATTEMPTS)
    parser.add_argument("--backoff-base", type=float, default=DEFAULT_BACKOFF_BASE_SEC)
    parser.add_argument(
        "--insecure",
        action="store_true",
        help="Disable TLS certificate verification (development only; do not use in production)",
    )
    args = parser.parse_args()

    mp = args.manifest or manifest_path_default()
    if args.insecure:
        print("WARNING: --insecure is set; TLS verification is disabled.", file=sys.stderr)
    print(f"User-Agent: {USER_AGENT}")
    print(f"Manifest: {mp.resolve()}")
    print(f"Timeout: {args.timeout}s | Stagger: {args.stagger}s | Max attempts: {args.max_attempts}")
    print()

    reports, _allowlist = fetch_all_allowlisted(
        manifest_path=mp,
        insecure=args.insecure,
        timeout_sec=args.timeout,
        stagger_sec=args.stagger,
        max_attempts=args.max_attempts,
        backoff_base_sec=args.backoff_base,
    )

    all_ok = True
    for r in reports:
        status = r.status_code if r.status_code is not None else "—"
        line = (
            f"[{'OK' if r.ok else 'FAIL'}] {r.source_id} | {r.amc_name}\n"
            f"         URL: {r.url}\n"
            f"         status={status} bytes={r.body_bytes} final_url={r.final_url!r} "
            f"content_type={r.content_type!r}"
        )
        if r.error:
            line += f"\n         error: {r.error}"
        print(line)
        if not r.ok:
            all_ok = False

    print()
    if all_ok:
        print("Phase 1.1 check: all five URLs returned HTTP 2xx.")
        return 0
    print("Phase 1.1 check: one or more URLs failed — see details above.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
