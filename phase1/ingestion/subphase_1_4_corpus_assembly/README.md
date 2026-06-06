# Phase 1.4 — Corpus assembly and manifest metadata

Implements [PhaseWiseArchitecture.md](../../../PhaseWiseArchitecture.md) §1.4.

## Purpose

Turn a Phase 1.1–1.3 ingest run into a **complete, Phase-2-ready corpus**:

- Validate all **five** allowlisted sources and required artifacts (`raw.html`, `snapshot_meta.json`, `clean.txt`)
- Bind each document to stable `id` and `source_url` / `canonical_url`
- Attach per-source **`fetched_at_utc`** (for Phase 3 “Last updated from sources” footer)
- Extract optional **`scheme_names_observed`** from clean text
- Write enriched **`ingest_manifest.json`** and single build output **`corpus.json`**
- Update **`config/corpus_manifest.json`** `last_fetch_at` and scheme names (unless disabled)

## Commands

**Assemble the latest run:**

```bash
python3 -m phase1.ingestion.subphase_1_4_corpus_assembly.run
```

**Assemble a specific run:**

```bash
python3 -m phase1.ingestion.subphase_1_4_corpus_assembly.run \
  --run-dir data/corpus_runs/<run_id>
```

**Full pipeline (1.1 → 1.4):**

```bash
python3 -m phase1.ingestion.ingest_through_1_4
```

## Outputs

Under `data/corpus_runs/<run_id>/`:

| File | Role |
|------|------|
| `ingest_manifest.json` | Enriched with `fetched_at_utc`, `scheme_names_observed`, `assembly_ok`, phase `1.4` |
| `corpus.json` | Single build artifact for Phase 2 — `documents[]` with stable IDs and citation URLs |

Root manifest side effect: `config/corpus_manifest.json` sources get `last_fetch_at` and `scheme_names_observed` updated on successful assembly.

## Exit criteria

- All five sources present with valid artifacts and minimum clean-text length
- No off-allowlist source directories in the run folder
- `corpus.json` written with `assembly_ok: true`
