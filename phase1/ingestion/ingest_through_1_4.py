#!/usr/bin/env python3
"""
Phase 1.1 + 1.2 + 1.3 + 1.4 pipeline: fetch → raw snapshots → clean text → corpus assembly.

From repository root:
  python3 -m phase1.ingestion.ingest_through_1_4

Writes under ``data/corpus_runs/<run_id>/``:
  - ``raw.html``, ``snapshot_meta.json`` (1.2)
  - ``clean.txt`` (1.3)
  - enriched ``ingest_manifest.json`` and ``corpus.json`` (1.4)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from phase1.ingestion.common.allowlist import manifest_path_default
from phase1.ingestion.ingest_through_1_3 import run_ingest
from phase1.ingestion.subphase_1_3_html_text.extract import DEFAULT_MIN_CLEAN_TEXT_CHARS
from phase1.ingestion.subphase_1_4_corpus_assembly.assembly import CORPUS_FILENAME, assemble_corpus


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest Phases 1.1–1.4")
    parser.add_argument("--manifest", type=Path, default=None)
    parser.add_argument("--runs-dir", type=Path, default=None, help="Default: data/corpus_runs")
    parser.add_argument("--run-id", type=str, default=None, help="Override auto UTC run id")
    parser.add_argument("--min-text-chars", type=int, default=DEFAULT_MIN_CLEAN_TEXT_CHARS)
    parser.add_argument("--insecure", action="store_true", help="Dev only: disable TLS verification")
    parser.add_argument(
        "--no-update-root-manifest",
        action="store_true",
        help="Do not update config/corpus_manifest.json last_fetch_at / scheme names",
    )
    args = parser.parse_args()

    ingest_code, run_dir = run_ingest(
        manifest=args.manifest,
        runs_dir=args.runs_dir,
        run_id=args.run_id,
        min_text_chars=args.min_text_chars,
        insecure=args.insecure,
    )
    if ingest_code != 0:
        return ingest_code

    mp = args.manifest or manifest_path_default()
    print()
    print("Phase 1.4 — corpus assembly")
    print("-" * 30)

    result = assemble_corpus(
        run_dir,
        manifest_path=mp,
        min_text_chars=args.min_text_chars,
        update_root_manifest=not args.no_update_root_manifest,
    )

    for doc in result.corpus.get("documents", []):
        schemes = doc.get("scheme_names_observed") or []
        print(
            f"[{'OK' if doc.get('assembly_ok') else 'FAIL'}] {doc['id']} "
            f"chars={doc.get('clean_text_chars')} schemes={len(schemes)}"
        )

    print()
    print(f"Wrote {run_dir / CORPUS_FILENAME}")
    if result.ok:
        print("Phase 1.1–1.4 ingest completed successfully.")
        return 0

    for err in result.errors:
        print(f"ERROR: {err}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
