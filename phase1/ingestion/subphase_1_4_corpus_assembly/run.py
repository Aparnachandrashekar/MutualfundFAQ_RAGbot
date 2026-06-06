#!/usr/bin/env python3
"""
Phase 1.4 CLI: assemble corpus metadata for an existing ingest run.

From repository root:
  python3 -m phase1.ingestion.subphase_1_4_corpus_assembly.run
  python3 -m phase1.ingestion.subphase_1_4_corpus_assembly.run --run-dir data/corpus_runs/<run_id>
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from phase1.ingestion.common.allowlist import manifest_path_default
from phase1.ingestion.common.paths import corpus_runs_dir, latest_corpus_run_dir
from phase1.ingestion.subphase_1_3_html_text.extract import DEFAULT_MIN_CLEAN_TEXT_CHARS
from phase1.ingestion.subphase_1_4_corpus_assembly.assembly import (
    CORPUS_FILENAME,
    assemble_corpus,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 1.4 — corpus assembly")
    parser.add_argument("--run-dir", type=Path, default=None, help="Ingest run directory")
    parser.add_argument("--runs-dir", type=Path, default=None, help="Default: data/corpus_runs")
    parser.add_argument("--manifest", type=Path, default=None)
    parser.add_argument("--min-text-chars", type=int, default=DEFAULT_MIN_CLEAN_TEXT_CHARS)
    parser.add_argument(
        "--no-update-root-manifest",
        action="store_true",
        help="Do not update config/corpus_manifest.json last_fetch_at / scheme names",
    )
    args = parser.parse_args()

    runs_root = args.runs_dir or corpus_runs_dir()
    if args.run_dir:
        run_dir = args.run_dir
    else:
        run_dir = latest_corpus_run_dir(runs_root)
        if run_dir is None:
            print(f"No ingest runs found under {runs_root}", file=sys.stderr)
            return 1

    if not run_dir.is_dir():
        print(f"Run directory not found: {run_dir}", file=sys.stderr)
        return 1

    mp = args.manifest or manifest_path_default()
    print(f"Run dir:   {run_dir.resolve()}")
    print(f"Manifest:  {mp.resolve()}")
    print(f"Min chars: {args.min_text_chars}")
    print()

    result = assemble_corpus(
        run_dir,
        manifest_path=mp,
        min_text_chars=args.min_text_chars,
        update_root_manifest=not args.no_update_root_manifest,
    )

    for doc in result.corpus.get("documents", []):
        schemes = doc.get("scheme_names_observed") or []
        scheme_note = f", schemes={len(schemes)}" if schemes else ""
        print(
            f"[{'OK' if doc.get('assembly_ok') else 'FAIL'}] {doc['id']} "
            f"chars={doc.get('clean_text_chars')}{scheme_note} "
            f"fetched={doc.get('fetched_at_utc')}"
        )

    print()
    print(f"Wrote {run_dir / CORPUS_FILENAME}")
    if result.ok:
        print("Phase 1.4 assembly completed successfully.")
        return 0

    for err in result.errors:
        print(f"ERROR: {err}", file=sys.stderr)
    print("Phase 1.4 assembly failed.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
