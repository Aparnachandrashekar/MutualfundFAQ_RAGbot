# Phase 1.5 — Validation, monitoring, and handoff checklist

Implements [PhaseWiseArchitecture.md](../../../PhaseWiseArchitecture.md) §1.5.

## Purpose

Quality gate between Phase 1 ingestion and Phase 2 chunking/indexing:

- **Structural checks**: five sources, Phase 1.4 `corpus.json` with `assembly_ok`, no off-allowlist dirs, required artifacts, 2048-char minimum
- **Semantic validation** with **bge-small-en** (`BAAI/bge-small-en-v1.5`):
  - Embed validation chunks (512-char sentence packing)
  - Financial relevance vs navigation contamination
  - Semantic coherence (chunk-to-centroid similarity)
  - Per-chunk embedding quality scores for Phase 2 pre-filtering
- **Handoff artifacts** for Phase 2

## Commands

```bash
# Validate latest assembled run
python3 -m phase1.ingestion.subphase_1_5_validation.run

# Validate specific run
python3 -m phase1.ingestion.subphase_1_5_validation.run \
  --run-dir data/corpus_runs/<run_id>

# Full pipeline 1.1 → 1.5
python3 -m phase1.ingestion.ingest_through_1_5
```

**Prerequisite:** Phase 1.4 must have run (`corpus.json` with `assembly_ok: true`).

## Outputs (per run directory)

| File | Purpose |
|------|---------|
| `validation_report.json` | Pass/fail, structural checks, per-source metrics, thresholds |
| `embedding_quality.json` | Per-source and per-chunk embedding quality scores for Phase 2 |
| `handoff_checklist.json` | Formal Phase 1 → Phase 2 handoff checklist |

`ingest_manifest.json` is updated with `phases` including `1.5`, `validated_at_utc`, and `validation_ok`.

## Validation metrics

| Metric | Threshold | Meaning |
|--------|-----------|---------|
| `content_quality` | ≥ 0.05 | Mean per-chunk (financial − navigation) score |
| `financial_relevance` | ≥ 0.55 | Mean chunk similarity to mutual fund terms |
| `navigation_contamination` | ≤ 0.72 | Mean chunk similarity to nav/trading boilerplate |
| `semantic_coherence` | ≥ 0.75 | Chunks align with corpus centroid |
| `embedding_quality` | ≥ 0.05 | Mean per-chunk embedding quality (Phase 2 pre-filter input) |
| `text_length` | ≥ 2048 | From Phase 1.3 minimum |

Thresholds are calibrated for `BAAI/bge-small-en-v1.5` (cosine similarity on normalized embeddings).

## Model

- **Model**: `BAAI/bge-small-en-v1.5` (same family as Phase 2 vector search)
- **Validation chunk size**: 512 characters (sentence accumulation — not Phase 2 retrieval chunks)
- **Embeddings**: L2-normalized for cosine similarity

## Operational notes

### Rerun after Groww HTML changes

1. Run full ingest: `python3 -m phase1.ingestion.ingest_through_1_5`
2. Or step-by-step:
   - `python3 -m phase1.ingestion.ingest_through_1_4` (fetch + assemble)
   - `python3 -m phase1.ingestion.subphase_1_5_validation.run --run-dir data/corpus_runs/<run_id>`
3. If validation fails, inspect `validation_report.json` per-source metrics
4. Phase 2 should pass `--validation-report` pointing at the new run's report

### CI integration

GitHub Actions runs Phase 1.5 after ingestion; exit code 1 fails the workflow.

## Phase 2 handoff

Phase 2 chunking reads `validation_report.json` for per-source `content_quality` scores to skip low-quality sources during indexing. Use:

```bash
python3 -m phase2.run_phase2 \
  --corpus-run data/corpus_runs/<run_id> \
  --validation-report data/corpus_runs/<run_id>/validation_report.json
```
