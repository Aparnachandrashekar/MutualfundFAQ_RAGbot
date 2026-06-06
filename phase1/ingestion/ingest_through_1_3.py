#!/usr/bin/env python3
"""
Phase 1.1 + 1.2 + 1.3 pipeline: fetch (allowlist) → raw snapshots → clean text.

From repository root:
  python3 -m phase1.ingestion.ingest_through_1_3

Writes under ``data/corpus_runs/<run_id>/<source_id>/``:
  - ``raw.html``, ``snapshot_meta.json`` (1.2)
  - ``clean.txt`` (1.3)

Exits non-zero if any fetch fails or clean text falls below minimum length.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from phase1.ingestion.common.allowlist import manifest_path_default
from phase1.ingestion.common.paths import corpus_runs_dir
from phase1.ingestion.subphase_1_1_fetch.fetch_layer import USER_AGENT, fetch_all_allowlisted
from phase1.ingestion.subphase_1_2_raw_snapshots.storage import (
    new_run_id,
    stored_snapshot_relative,
    write_raw_snapshot,
)
from phase1.ingestion.subphase_1_3_html_text.extract import (
    DEFAULT_MIN_CLEAN_TEXT_CHARS,
    check_min_length,
    html_bytes_to_normalized_text,
)

CLEAN_FILENAME = "clean.txt"
MANIFEST_FILENAME = "ingest_manifest.json"


def run_ingest(
    *,
    manifest: Path | None = None,
    runs_dir: Path | None = None,
    run_id: str | None = None,
    min_text_chars: int = DEFAULT_MIN_CLEAN_TEXT_CHARS,
    insecure: bool = False,
) -> tuple[int, Path]:
    """Run Phases 1.1–1.3; return ``(exit_code, run_dir)``."""
    mp = manifest or manifest_path_default()
    runs_root = runs_dir or corpus_runs_dir()
    resolved_run_id = run_id or new_run_id()
    run_dir = runs_root / resolved_run_id
    runs_root.mkdir(parents=True, exist_ok=True)
    run_dir.mkdir(parents=False, exist_ok=False)

    if insecure:
        print("WARNING: --insecure is set.", file=sys.stderr)

    created_at = datetime.now(timezone.utc).isoformat()
    print(f"Run id:      {resolved_run_id}")
    print(f"Output dir:  {run_dir}")
    print(f"User-Agent:  {USER_AGENT}")
    print(f"Manifest:    {mp.resolve()}")
    print(f"Min chars:   {min_text_chars} (clean text sanity)")
    print()

    reports, _allow = fetch_all_allowlisted(
        manifest_path=mp,
        insecure=insecure,
        capture_body=True,
    )

    manifest_sources: list[dict[str, object]] = []
    any_fetch_fail = False
    any_text_fail = False

    for r in reports:
        rel = stored_snapshot_relative(r.source_id)
        entry: dict[str, object] = {
            "id": r.source_id,
            "amc_name": r.amc_name,
            "canonical_url": r.url,
            "fetch_ok": r.ok,
        }

        if not r.ok or not r.raw_body:
            any_fetch_fail = True
            entry["error"] = r.error or "missing body"
            entry["raw_html_path"] = None
            entry["snapshot_meta_path"] = None
            entry["clean_text_path"] = None
            entry["clean_text_chars"] = 0
            entry["extraction_ok"] = False
            manifest_sources.append(entry)
            print(f"[FETCH FAIL] {r.source_id} — {entry['error']}")
            continue

        write_raw_snapshot(run_dir, r, fetched_at_utc=created_at)
        clean_rel = Path(rel["raw_html_path"]).parent / CLEAN_FILENAME

        raw_path = run_dir / rel["raw_html_path"]
        text = html_bytes_to_normalized_text(
            r.raw_body,
            content_type_header=r.content_type_header,
        )
        clean_path = run_dir / clean_rel
        clean_path.write_text(text, encoding="utf-8")

        long_enough = check_min_length(text, minimum=min_text_chars)
        if not long_enough:
            any_text_fail = True

        entry["raw_html_path"] = rel["raw_html_path"]
        entry["snapshot_meta_path"] = rel["snapshot_meta_path"]
        entry["clean_text_path"] = str(clean_rel).replace("\\", "/")
        entry["clean_text_chars"] = len(text)
        entry["extraction_ok"] = long_enough
        manifest_sources.append(entry)

        flag = "OK" if long_enough else "SHORT TEXT"
        print(f"[{flag}] {r.source_id} raw={raw_path.stat().st_size}b clean={len(text)} chars")

    root_manifest = {
        "run_id": resolved_run_id,
        "created_at_utc": created_at,
        "phases": ["1.1", "1.2", "1.3"],
        "manifest_path": str(mp.resolve()),
        "min_clean_text_chars": min_text_chars,
        "sources": manifest_sources,
    }
    (run_dir / MANIFEST_FILENAME).write_text(
        json.dumps(root_manifest, indent=2),
        encoding="utf-8",
    )

    print()
    print(f"Wrote {run_dir / MANIFEST_FILENAME}")
    if any_fetch_fail or any_text_fail:
        if any_fetch_fail:
            print("Exit 1: one or more fetches failed.", file=sys.stderr)
        if any_text_fail:
            print(
                f"Exit 1: one or more clean texts shorter than {min_text_chars} chars.",
                file=sys.stderr,
            )
        return 1, run_dir
    print("Phase 1.1–1.3 ingest completed successfully.")
    return 0, run_dir


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest Phases 1.1–1.3")
    parser.add_argument("--manifest", type=Path, default=None)
    parser.add_argument("--runs-dir", type=Path, default=None, help="Default: data/corpus_runs")
    parser.add_argument("--run-id", type=str, default=None, help="Override auto UTC run id")
    parser.add_argument("--min-text-chars", type=int, default=DEFAULT_MIN_CLEAN_TEXT_CHARS)
    parser.add_argument("--insecure", action="store_true", help="Dev only: disable TLS verification")
    args = parser.parse_args()
    exit_code, _run_dir = run_ingest(
        manifest=args.manifest,
        runs_dir=args.runs_dir,
        run_id=args.run_id,
        min_text_chars=args.min_text_chars,
        insecure=args.insecure,
    )
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
