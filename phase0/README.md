# Phase 0 — Corpus design and compliance baseline

Implements [Phase 0 in PhaseWiseArchitecture.md](../PhaseWiseArchitecture.md).

## Contents

| Artifact | Purpose |
|----------|---------|
| [`../config/corpus_manifest.json`](../config/corpus_manifest.json) | **Source manifest:** the only five corpus URLs (`sources[].url`). Optional `scheme_names_observed` and `last_fetch_at` filled in Phase 1+. |
| [`../config/corpus_manifest.schema.json`](../config/corpus_manifest.schema.json) | JSON Schema; enforces exactly five sources for this project. |
| [`refusal_taxonomy.json`](./refusal_taxonomy.json) | Refusal categories, examples, and **educational** link allowlist for refusal flows (not RAG corpus). |
| [`compliance_checklist.md`](./compliance_checklist.md) | Privacy, facts-only, and transparency checklist with sign-off table. |
| [`query_scope.md`](./query_scope.md) | Factual vs out-of-scope rules and mixed-query handling. |

## Exit criteria (Phase 0)

- [x] Ingestion allowlist documented as **these five URLs only** (`corpus_manifest.json`).
- [x] Rules for factual vs out-of-scope documented (`query_scope.md`).
- [x] Refusal taxonomy and safe educational redirects documented (`refusal_taxonomy.json`).
- [x] Compliance checklist ready for sign-off (`compliance_checklist.md`).

## Validation

From repo root:

```bash
python3 scripts/validate_corpus_manifest.py
```

Expect: `OK: corpus_manifest.json matches Phase 0 rules.`

## Phase folders

Implementation work for later phases lives under `phase1/` … `phase5/` (see each folder’s README).
