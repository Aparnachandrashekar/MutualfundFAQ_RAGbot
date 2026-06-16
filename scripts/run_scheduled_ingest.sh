#!/usr/bin/env bash
# Local mirror of .github/workflows/ingestion.yml (ingest-and-validate job).
# Usage: ./scripts/run_scheduled_ingest.sh [--skip-phase2]
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

MIN_TEXT_CHARS="${MIN_TEXT_CHARS:-2048}"
SKIP_PHASE2=false

for arg in "$@"; do
  case "$arg" in
    --skip-phase2) SKIP_PHASE2=true ;;
    -h|--help)
      echo "Usage: $0 [--skip-phase2]"
      echo "Runs Phase 1.1–1.4 ingest, Phase 1.5 validation, and optional Phase 2 rebuild."
      exit 0
      ;;
    *)
      echo "Unknown argument: $arg" >&2
      exit 1
      ;;
  esac
done

echo "============================================================"
echo "Scheduled ingest (local)"
echo "============================================================"
echo "Repo:       $ROOT"
echo "Min chars:  $MIN_TEXT_CHARS"
echo

mkdir -p data/corpus_runs

echo "Step 1/4 — Phase 1.1–1.4 ingestion"
python3 -m phase1.ingestion.ingest_through_1_4 --min-text-chars "$MIN_TEXT_CHARS"

echo
echo "Step 2/4 — Phase 1.5 semantic validation"
python3 -m phase1.ingestion.subphase_1_5_validation.run --min-text-chars "$MIN_TEXT_CHARS"

LATEST_RUN="$(python3 - <<'PY'
from phase1.ingestion.common.paths import latest_corpus_run_dir
run = latest_corpus_run_dir()
if run is None:
    raise SystemExit("No corpus run directory found")
print(run)
PY
)"
echo
echo "Latest run: $LATEST_RUN"

echo
echo "Step 3/4 — Post-ingest checks"
python3 - <<PY
import json
import sys
from pathlib import Path

run_dir = Path("$LATEST_RUN")
report_path = run_dir / "validation_report.json"
if not report_path.is_file():
    print("❌ validation_report.json not found", file=sys.stderr)
    sys.exit(1)

report = json.loads(report_path.read_text(encoding="utf-8"))
validation_ok = bool(report.get("validation_ok"))
source_count = len(list(run_dir.glob("*/clean.txt")))
manifest_path = Path("config/corpus_manifest.json")
expected_count = len(json.loads(manifest_path.read_text(encoding="utf-8")).get("sources", []))

print(f"validation_ok: {validation_ok}")
print(f"clean.txt files: {source_count}/{expected_count}")

if not validation_ok:
    print("❌ Validation failed", file=sys.stderr)
    sys.exit(1)
if source_count != expected_count:
    print(f"❌ Expected {expected_count} sources, found {source_count}", file=sys.stderr)
    sys.exit(1)

manifest = json.loads((run_dir / "ingest_manifest.json").read_text(encoding="utf-8"))
summary = {
    "run_id": manifest.get("run_id"),
    "created_at": manifest.get("created_at_utc"),
    "validation_ok": validation_ok,
    "total_sources": report["summary"]["total_sources"],
    "passed_sources": report["summary"]["passed_sources"],
    "total_characters": report["summary"]["total_characters"],
    "avg_content_quality": round(report["summary"]["avg_content_quality"], 3),
    "model_used": report["summary"]["model_used"],
}
(run_dir / "run_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
print("✅ Ingestion checks passed")
print(json.dumps(summary, indent=2))
PY

if [[ "$SKIP_PHASE2" == false ]]; then
  echo
  echo "Step 4/4 — Phase 2 index rebuild"
  python3 -m phase2.rag.run_pipeline \
    --corpus-run "$LATEST_RUN" \
    --output-dir data/phase2_results
else
  echo
  echo "Step 4/4 — skipped (--skip-phase2)"
fi

echo
echo "============================================================"
echo "Scheduled ingest completed successfully"
echo "Run directory: $LATEST_RUN"
echo "============================================================"
