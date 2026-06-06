#!/usr/bin/env python3
"""
Phase 1.1–1.5 full ingestion pipeline: fetch → raw → text → assembly → validation.

From repository root:
  python3 -m phase1.ingestion.ingest_through_1_5
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from phase1.ingestion.common.allowlist import manifest_path_default
from phase1.ingestion.ingest_through_1_3 import run_ingest
from phase1.ingestion.subphase_1_3_html_text.extract import DEFAULT_MIN_CLEAN_TEXT_CHARS
from phase1.ingestion.subphase_1_4_corpus_assembly.assembly import assemble_corpus
from phase1.ingestion.subphase_1_5_validation.validation import SemanticValidator, validate_run


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest Phases 1.1–1.5")
    parser.add_argument("--manifest", type=Path, default=None)
    parser.add_argument("--runs-dir", type=Path, default=None)
    parser.add_argument("--run-id", type=str, default=None)
    parser.add_argument("--min-text-chars", type=int, default=DEFAULT_MIN_CLEAN_TEXT_CHARS)
    parser.add_argument("--insecure", action="store_true")
    parser.add_argument(
        "--no-update-root-manifest",
        action="store_true",
        help="Do not update config/corpus_manifest.json during Phase 1.4",
    )
    args = parser.parse_args()

    mp = args.manifest or manifest_path_default()

    ingest_code, run_dir = run_ingest(
        manifest=mp,
        runs_dir=args.runs_dir,
        run_id=args.run_id,
        min_text_chars=args.min_text_chars,
        insecure=args.insecure,
    )
    if ingest_code != 0:
        return ingest_code

    print()
    print("Phase 1.4 — corpus assembly")
    print("-" * 30)
    assembly = assemble_corpus(
        run_dir,
        manifest_path=mp,
        min_text_chars=args.min_text_chars,
        update_root_manifest=not args.no_update_root_manifest,
    )
    if not assembly.ok:
        for err in assembly.errors:
            print(f"ERROR: {err}", file=sys.stderr)
        return 1

    print()
    print("Phase 1.5 — validation")
    print("-" * 30)
    result = validate_run(
        run_dir,
        validator=SemanticValidator(),
        min_text_chars=args.min_text_chars,
        manifest_path=mp,
    )
    if result.ok:
        print("Phase 1.1–1.5 ingest completed successfully.")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
