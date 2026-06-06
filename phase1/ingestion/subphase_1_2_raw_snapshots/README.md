# Phase 1.2 — Raw snapshot storage

See [PhaseWiseArchitecture.md](../../../PhaseWiseArchitecture.md) §1.2.

**Implemented** in [`storage.py`](./storage.py):

- Per ingest **run**, under `data/corpus_runs/<run_id>/<source_id>/`:
  - `raw.html` — immutable bytes returned for a successful 2xx GET
  - `snapshot_meta.json` — `status_code`, `final_url`, `content_type`, full `Content-Type` header, `body_bytes`, `fetched_at_utc`, canonical URL

**Typical invocation:** [`ingest_through_1_3.py`](../ingest_through_1_3.py) (runs 1.1 → 1.2 → 1.3).

**Exit criterion:** Every clean-text line in Phase 1.3 traces to a saved `raw.html` row in `ingest_manifest.json`.
