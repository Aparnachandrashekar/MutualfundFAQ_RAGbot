# Phase 2 — Chunking, indexing, and retrieval (RAG core)

Implements the **BM25-first hybrid strategy** from [PhaseWiseArchitecture.md](../PhaseWiseArchitecture.md) §2.

## Strategy summary

| Component | Setting |
|-----------|---------|
| Chunk size | 300–400 chars, 50 overlap |
| Pre-index filter | Drop nav/calculator; `financial_density ≥ 0.05` |
| Hybrid fusion | **75% BM25 + 25% vector** via **RRF** |
| Embedding model | `BAAI/bge-small-en-v1.5` |
| Vector index | **FAISS IndexFlatIP** (~100 vectors) |
| Query routing | **AMC hard filter** when AMC named |
| Top-k | 5 (for Phase 3) |

## Run pipeline

```bash
python3 -m phase2.run_phase2 \
  --corpus-run data/corpus_runs/<run_id> \
  --output-dir data/phase2_results
```

Auto-loads `validation_report.json` from the corpus run if present.

## Test retrieval

```bash
python3 -m phase2.rag.retrieval \
  --load-index data/phase2_results/retrieval \
  --query "What is the exit load for Union Flexi Cap Fund?" \
  --top-k 5
```

## Outputs

```
data/phase2_results/
├── chunks/chunks.json
├── indexes/vector_index.faiss
├── retrieval/              # BM25 + FAISS bundle for serving
└── phase2_pipeline_report.json
```

## Modules

| File | Role |
|------|------|
| `config.py` | Shared defaults (weights, model, chunk sizes) |
| `chunking.py` | Smart chunking + quality filter |
| `indexing.py` | FAISS flat index builder |
| `retrieval.py` | HybridRetriever (RRF + AMC routing) |
| `run_pipeline.py` | End-to-end orchestrator |
