# Phase 1 — Ingestion (sub-phase layout)

Implements [PhaseWiseArchitecture.md](../../PhaseWiseArchitecture.md) §1 (1.1–1.5).

## Directory map

| Folder | Sub-phase | Role |
|--------|-----------|------|
| [`common/`](./common/) | Shared | Manifest, allowlist, `corpus_runs_dir()` |
| [`subphase_1_1_fetch/`](./subphase_1_1_fetch/) | 1.1 | Allowlist HTTP GET (+ optional `capture_body`) |
| [`subphase_1_2_raw_snapshots/`](./subphase_1_2_raw_snapshots/) | 1.2 | `raw.html` + `snapshot_meta.json` |
| [`subphase_1_3_html_text/`](./subphase_1_3_html_text/) | 1.3 | `clean.txt` (normalized plain text) |
| [`subphase_1_4_corpus_assembly/`](./subphase_1_4_corpus_assembly/) | 1.4 | `corpus.json` + enriched manifest metadata |
| [`subphase_1_5_validation/`](./subphase_1_5_validation/) | 1.5 | Semantic validation with bge-small-en embeddings |

## Dependencies

```bash
python3 -m pip install -r requirements.txt
```

## Commands (repo root)

| Command | Purpose |
|---------|---------|
| `python3 -m phase1.ingestion.subphase_1_1_fetch.run` | Phase **1.1** only — connectivity check |
| `python3 -m phase1.ingestion.ingest_through_1_3` | **1.1 + 1.2 + 1.3** — fetch, save raw, extract `clean.txt` |
| `python3 -m phase1.ingestion.subphase_1_4_corpus_assembly.run` | **1.4** — assemble existing run |
| `python3 -m phase1.ingestion.ingest_through_1_4` | **1.1 → 1.4** — full ingest + assembly |
| `python3 -m phase1.ingestion.subphase_1_5_validation.run` | **1.5** — semantic validation (requires 1.4) |
| `python3 -m phase1.ingestion.ingest_through_1_5` | **1.1 → 1.5** — full ingest + validation |

Artifacts: **`data/corpus_runs/<run_id>/`** (gitignored — see [.gitignore](../../.gitignore)). Each source has `raw.html`, `snapshot_meta.json`, `clean.txt`, plus `ingest_manifest.json`, `corpus.json`, `validation_report.json`, `embedding_quality.json`, and `handoff_checklist.json`.

### Pipeline flags

`--runs-dir`, `--run-id`, `--manifest`, `--min-text-chars` (default 2048), `--insecure` (dev only), `--no-update-root-manifest` (1.4 only).

## Importing

```python
from phase1.ingestion.subphase_1_4_corpus_assembly import assemble_corpus
from phase1.ingestion.subphase_1_2_raw_snapshots import write_raw_snapshot, new_run_id
from phase1.ingestion.subphase_1_3_html_text import html_bytes_to_normalized_text
```

**Exit criteria (Phase 1 overall):** all five sources in the corpus; no off-allowlist URLs; `corpus.json` assembly passes.

## Automation and Scheduling

### GitHub Actions Integration

**Automated daily ingestion** via GitHub Actions workflow:

- **Schedule**: Daily at **10:00 AM IST** (04:30 UTC)
- **Pipeline**: 1.1 → 1.2 → 1.3 → 1.4 → 1.5 validation
- **Quality Gates**: Automatic failure on validation errors
- **Version Control**: Each run committed with timestamped artifacts
- **Cleanup**: Automatic cleanup of runs older than 7 days

### Workflow Features:

🔄 **Automated Execution**:
```yaml
# Daily at 10:00 AM IST (04:30 UTC)
schedule:
  - cron: '30 4 * * *'
# Manual dispatch for urgent updates  
workflow_dispatch:
```

📊 **Quality Assurance**:
- Semantic validation with bge-small-en embeddings
- Content quality scoring and thresholds
- Automatic rollback on validation failures

📋 **Audit Trail**:
- JSON validation reports per run
- Source-by-source quality metrics
- Historical run tracking and comparison

### Manual Operations:

**Trigger manual ingestion**:
```bash
# Via GitHub Actions UI
# Repository → Actions → "Automated Corpus Ingestion and Validation" → "Run workflow"

# Or via GitHub CLI
gh workflow run ingestion.yml
```

**Monitor recent runs**:
```bash
# Check latest ingestion results
find data/corpus_runs -name "validation_report.json" -exec cat {} \; | jq '.summary'

# View run history
ls -la data/corpus_runs/ | tail -10
```

**Exit criteria (Phase 1 overall):** all five sources in the corpus; no off-allowlist URLs; automated validation passes.
