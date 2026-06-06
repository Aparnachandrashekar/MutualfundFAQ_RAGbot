# Mutual Fund FAQ Assistant — Phase-Wise Architecture

This document breaks the system described in the problem statement into ordered phases, each with goals, components, and exit criteria. The design prioritizes **facts-only answers** and **transparent citations** over open-ended helpfulness.

**Project corpus constraint:** ingestion and citations use **only** the five URLs listed in Phase 0—no additional AMC, AMFI, or SEBI pages unless you explicitly expand the allowlist later.

---

## Phase 0 — Corpus design and compliance baseline

**Goals**

- Lock scope across **five AMCs** using **exactly** the URLs below—the **complete and final allowlist** for this project (no other pages ingested or cited as corpus sources).
- Use those pages to understand which schemes appear on each AMC overview and to scope FAQ coverage (e.g., index vs flexi-cap vs hybrid vs debt); retrieval is still limited to text extracted from these five URLs only.
- Write the **refusal taxonomy** (advisory, comparison, “what should I buy”) and **safe redirect** targets (AMFI/SEBI educational links for refusals—external links that are not part of the RAG corpus are allowed here per product rules).

**Corpus URLs (only sources — 5 total)**

| AMC | URL |
|-----|-----|
| Choice Mutual Fund | [https://groww.in/mutual-funds/amc/choice-mutual-funds](https://groww.in/mutual-funds/amc/choice-mutual-funds) |
| Unifi Mutual Fund | [https://groww.in/mutual-funds/amc/unifi-mutual-funds](https://groww.in/mutual-funds/amc/unifi-mutual-funds) |
| Union Mutual Fund | [https://groww.in/mutual-funds/amc/union-mutual-funds](https://groww.in/mutual-funds/amc/union-mutual-funds) |
| ICICI Prudential Mutual Fund | [https://groww.in/mutual-funds/amc/icici-prudential-mutual-funds](https://groww.in/mutual-funds/amc/icici-prudential-mutual-funds) |
| LIC Mutual Fund | [https://groww.in/mutual-funds/amc/lic-mutual-funds](https://groww.in/mutual-funds/amc/lic-mutual-funds) |

**Components**

- Source manifest fixed to the five rows above (optional metadata: scheme names observed per page, last fetch time).
- Compliance checklist: no PII collection; facts-only behavior unchanged even though the corpus is narrow.

**Exit criteria**

- Ingestion allowlist signed off as **these five URLs only**; documented rules for factual vs out-of-scope queries.

---

## Phase 1 — Ingestion and curated knowledge base

**Goals**

- Fetch and normalize content **only** from allowlisted URLs.
- Produce a versioned, auditable raw corpus (HTML/PDF text extraction as needed) and metadata (source URL, document type, fetch date).

**Components** (overall)

- Crawler or scheduled fetcher with **domain/path allowlist** and robots/respectful rate limits.
- Parsers: HTML → text for these pages (no extra PDFs or documents unless you later add URLs).
- Storage: raw artifacts + cleaned text + **last-ingested timestamp** per source (supports “Last updated from sources” in answers).
- **Scheduler (production):** [GitHub Actions](#automation-and-scheduling-github-actions) runs the full ingest pipeline on a daily cron so the corpus always reflects the latest Groww AMC pages (see § Automation and Scheduling).

**Phase 1 sub-phases** (implement **in order**, one sub-phase at a time)

### 1.1 — Fetch layer and allowlist enforcement

- Wire requests **only** to URLs in Phase 0 / `corpus_manifest.json`; reject any URL not in that set at runtime.
- Respectful fetching: timeouts, retries with backoff, clear `User-Agent`, optional stagger between the five URLs to avoid bursts.
- **Exit:** Successfully retrieve HTTP responses for each of the five URLs (or explicit per-URL error reporting with no silent drops).

### 1.2 — Raw snapshot storage

- Persist immutable **raw HTML** (or raw response body) per source per ingest run—path or object naming keyed by source `id` and run timestamp.
- Preserve response metadata useful for debugging: status code, final URL after redirects if allowed, Content-Type.
- **Exit:** Audit trail exists so any extracted text can be traced to a saved raw artifact.

### 1.3 — HTML → text extraction and normalization

- Parse HTML only; strip navigation, footer, scripts, cookie banners where feasible to reduce retrieval noise.
- Normalize Unicode / whitespace for stable downstream chunking (Phase 2).
- **Exit:** One **clean text** artifact per canonical source URL with minimum length / sanity checks so empty or accidental error pages are not treated as corpus.

### 1.4 — Corpus assembly and manifest metadata

- **Data structure**: `data/corpus_runs/<run_id>/` with timestamped run IDs (e.g., `20260503T064957_082350Z`)
- **Per-source artifacts**: Each AMC (`groww_amc_*`) contains:
  - `clean.txt` - normalized plain text (13K-25K characters per source)
  - `raw.html` - immutable raw HTML snapshot
  - `snapshot_meta.json` - fetch metadata (status, URLs, content-type, body size)
- **Run-level manifest**: `ingest_manifest.json` containing:
  - Run metadata: `run_id`, `created_at_utc`, phases completed
  - Source array with: `id`, `amc_name`, `canonical_url`, file paths, character counts, validation status
- **Stable identifiers**: Internal IDs (`groww_amc_choice`, `groww_amc_unifi`, etc.) map to canonical URLs
- **Timestamp tracking**: `fetched_at_utc` per source for Phase 3 "Last updated from sources" footer
- **Exit:** Complete run directory with all 5 sources, validation metadata, and clean text ready for Phase 2 chunking

### 1.5 — Validation, monitoring, handoff checklist

- **Semantic validation using bge-small-en**:
  - Embed clean text chunks to verify semantic coherence and content quality
  - Detect navigation/footer contamination through similarity analysis
  - Validate that extracted content contains substantive mutual fund information
  - Generate embedding quality scores for Phase 2 chunking preparation
- **Automated checks**: five sources present; no off-allowlist files; minimum text length thresholds (2048 chars); embedding quality thresholds.
- **Content validation**: Verify presence of key mutual fund terms (NAV, schemes, performance data) using semantic similarity.
- **Monitoring outputs**: Validation report with embedding scores, content quality metrics, and any flagged issues.
- **Operational documentation**: How to rerun ingestion after Groww HTML changes; embedding model version tracking.
- **Exit:** Phase 1 done when all validation checks pass, embedding quality meets thresholds, and handoff to Phase 2 includes clean text + embeddings for chunking.

**Exit criteria (Phase 1 overall)**

- All **five** allowlisted sources represented in the corpus with stable identifiers linking back to **exactly one canonical URL** per chunk policy (defined in Phase 2).
- No URLs outside the five-page allowlist and no user-submitted content in the pipeline.

---

## Phase 2 — Chunking, indexing, and retrieval (RAG core)

**Goals**

- Split documents into retrieval units that stay faithful to one primary topic (e.g., exit load, expense ratio) where possible.
- Build a **BM25-first hybrid retrieval system** tuned for a **small, sparse corpus** (~100K chars, five AMC overview pages).
- Enable high-quality retrieval with **deterministic citation URLs** (one of the five corpus URLs) for Phase 3 generation.

**Data-driven strategy** (validated against Phase 1 corpus runs):

| Corpus trait | Retrieval implication |
|--------------|----------------------|
| ~98K chars, ~200–300 chunks | Pre-filtering beats fancy indexes; **FAISS Flat** sufficient |
| Five AMC sources, one URL each | **AMC hard-routing** when AMC named in query |
| Table-like MF facts (NAV, exit load, SIP) | **BM25-heavy** hybrid (75% / 25%) |
| Groww nav residue in clean text | Drop nav/calculator chunks; use Phase 1.5 quality signals |
| bge-small-en weak fin-vs-nav margin | Vector is **secondary**; RRF fusion over raw score sum |

**Components**

### **Smart Chunking Strategy**
- **Size**: **300–400 characters** per chunk (lower end for sparse table data)
- **Overlap**: **50 characters** between consecutive chunks
- **Semantic boundaries**: Sentence-aware splits; skip leading nav boilerplate (start at scheme listing where possible)
- **Pre-filtering before index**:
  - Drop `content_type = navigation` or `calculator`
  - Drop chunks with `financial_density < 0.05`
  - Skip sources failing Phase 1.5 validation (`content_quality < 0.05`)

### **Hybrid Retrieval Architecture**
- **Primary**: BM25 ( **75%** rank contribution ) for exact financial terms — NAV, expense ratio, exit load, fund names
- **Secondary**: Vector search ( **25%** ) using **`BAAI/bge-small-en-v1.5`** (same model family as Phase 1.5)
- **Fusion**: **Reciprocal Rank Fusion (RRF)** across BM25 and vector ranked lists (robust on small corpora)
- **AMC hard filter**: When query names an AMC → search **only that AMC's chunks** (maps to one citation URL)
- **Re-ranking boosts** after fusion:
  - `× 1.2` for `content_type = fund_info`
  - `× 0.5` for `content_type = navigation`
  - `× (1 + financial_density × 0.5)`
  - `× 1.3` when query fund name matches chunk entities

### **Metadata Enrichment**
```json
{
  "source_id": "groww_amc_choice",
  "source_url": "https://groww.in/mutual-funds/amc/choice-mutual-funds",
  "amc_name": "Choice Mutual Fund",
  "content_type": "fund_info|navigation|calculator|mixed",
  "entities": ["Choice Nifty 50 Index Fund", "NAV", "SIP"],
  "financial_density": 0.08,
  "ingested_at": "2026-05-03T06:49:57.082716+00:00"
}
```

### **Query Processing Pipeline**
1. **Entity extraction** — AMC aliases, fund types, financial concepts, fund names
2. **AMC hard filter** — restrict candidate chunks when AMC detected (highest precision win)
3. **Hybrid search** — BM25 + bge-small-en vector on quality-filtered index
4. **RRF fusion** — merge ranked lists (default `k=60`)
5. **Metadata re-rank** — financial density, content type, fund-name match
6. **Top-k = 3–5** — dedupe by `source_url`; pass to Phase 3 with citation metadata

### **Retrieval Configuration**
- **BM25**: `BM25Okapi` over tokenized chunks
- **Vector**: `BAAI/bge-small-en-v1.5` (384D), L2-normalized, cosine via inner product
- **Index**: **FAISS IndexFlatIP** (flat — corpus is ~300 vectors; IVF unnecessary)
- **Defaults**: `BM25_WEIGHT=0.75`, `VECTOR_WEIGHT=0.25`, `DEFAULT_TOP_K=5`
- **Implementation**: `phase2/rag/` — `chunking.py`, `retrieval.py`, `indexing.py`, `run_pipeline.py`

**Exit criteria**

- Retrieval returns chunks whose **citation URL** is one of the **five** corpus URLs (deterministic via `source_url` metadata).
- Navigation-heavy chunks excluded from index (target **60%+** nav noise reduction vs raw clean text).
- Measured on golden FAQ queries: AMC routing returns chunks from the correct AMC page.
- Phase 3 receives **top 3–5** chunks with `ingested_at` for footer generation.

---

## Phase 3 — Generation, formatting, and guardrails

**Goals**

- Generate answers that are **max three sentences**, include **exactly one citation link** (only when a grounded answer is found), and append the footer:  
  `Last updated from sources: <date>` (date derived from corpus/metadata policy—e.g., max `ingested_at` among used chunks).
- **Handle no-answer scenarios**: When the corpus does not contain relevant information, respond with a fixed no-information message **without attaching any URL** — no citation, no footer, no educational link.
- **Privacy protection**: For queries involving personal information, account access, or PII — refuse with a privacy notice and **attach no URLs of any kind** (no citation, no educational link, no footer).
- **Refuse** advisory or comparative queries with a polite message, facts-only reminder, and **one educational link** (AMFI/SEBI only — external, not corpus).

**Components**

- **Intent classification**: Distinguish between factual FAQ, advisory, comparison, personal-information, and out-of-scope queries.
- **Answer generation**: Facts-only responses using retrieved chunks, max three sentences, no performance comparisons or return calculations. Uses simple extraction by default; optional **Groq** LLM (`llama-3.3-70b-versatile` by default) when `GROQ_API_KEY` is set.
- **Evidence gate**: Before citing, require sufficient retrieval evidence (minimum score + query–chunk term overlap). If the gate fails → treat as **no answer** (no URLs).
- **Citation policy**:
  - **When answer found and grounded**: Map to **exactly one** `source_url`, always one of the **five** corpus URLs
  - **When no answer found**: **No URLs** — citation, footer, and educational link all empty
  - **Personal information queries**: **No URLs** — privacy refusal only
  - **Privacy filter**: Never include URLs with personal data, account access, login, or user-specific content
- **Refusal templates**: Pre-defined responses for advisory, comparative, personal-information, and no-information requests (from `phase0/refusal_taxonomy.json`).
- **Footer generation**: Dynamic "Last updated" based on chunk metadata — **only** when a cited answer is provided.

**Query Handling Logic:**

| Scenario | Response | Citation | Footer | Educational link |
|----------|----------|----------|--------|------------------|
| Factual + grounded chunks | Answer (≤3 sentences) | One corpus URL | `Last updated from sources: <date>` | — |
| Factual + no relevant chunks | "I don't have information about that in my current data." | **None** | **None** | **None** |
| Advisory query | Polite refusal + facts-only reminder | — | — | One AMFI/SEBI link |
| Comparison query | Polite refusal + facts-only reminder | — | — | One AMFI/SEBI link |
| Personal information request | Privacy refusal | **None** | **None** | **None** |

**Implementation**: `phase3/generation/` — `config.py`, `intent_classifier.py`, `guardrails.py`, `answer_generator.py`, `run_pipeline.py`

**Exit criteria**

- Automated or manual evaluation shows: correct refusals on advisory prompts; factual prompts answered with citations only when grounded; **no URLs** on unknown-answer or personal-information paths; no advice language in outputs.

---

## Phase 4 — Minimal user interface

**Goals**

- Ship a **simple** UI: welcome message, **three example questions**, visible disclaimer: **“Facts-only. No investment advice.”**
- Do not collect PAN, Aadhaar, account numbers, OTPs, email, or phone numbers (no forms that elicit PII).

**Components**

- Thin frontend (e.g., single-page chat) calling a backend `/query` endpoint.
- Static disclaimer and optional “how citations work” microcopy.

**Exit criteria**

- End-to-end demo: user asks question → sees compliant answer or refusal → citation and last-updated footer behave as specified.

---

## Phase 5 — Packaging, documentation, and operational clarity

**Goals**

- README with setup steps, selected AMCs (five), the **complete list of five corpus URLs**, **RAG architecture summary**, and **known limitations** (including that answers are grounded only in those pages).
- Reusable **disclaimer snippet** for README/UI.
- Optional: simple `docker-compose` or scripts for local run; document embedding/API keys and index build.

**Components**

- README, environment example (without secrets), ingestion/reindex instructions.

**Exit criteria**

- A new developer can run the app, rebuild the index after source updates, and understand boundaries of the system.

---

## End-to-end logical architecture (reference)

```text
Allowlisted URLs
      │
      ▼
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────────┐
│ Ingest + parse  │ ──▶ │ Chunk + embed    │ ──▶ │ Vector index + meta │
└─────────────────┘     └──────────────────┘     └──────────┬──────────┘
                                                             │
User query ──▶ ┌──────────────────┐     ┌────────────────────┴────────────┐
               │ Intent / safety  │ ──▶ │ Retrieve top-k (scheme filters) │
               │ (FAQ vs refuse)  │     └────────────────────┬────────────┘
               └────────┬─────────┘                          │
                        │                                   ▼
                        │                          ┌─────────────────┐
                        └────────────────────────▶│ Groq + citation │
                                                  │ 3 sentences max │
                                                  │ 1 source link   │
                                                  │ + last updated  │
                                                  └────────┬────────┘
                                                           ▼
                                                    Response to UI
```

---

## Automation and Scheduling (GitHub Actions)

**GitHub Actions is the scheduler for keeping corpus data fresh.** It re-fetches all five allowlisted Groww AMC URLs on a fixed schedule, runs the full Phase 1 pipeline, validates output, and commits the latest run to the repository—no manual cron server required.

**Workflow file:** [`.github/workflows/ingestion.yml`](.github/workflows/ingestion.yml)

### Why GitHub Actions

| Benefit | How |
|--------|-----|
| **Always latest data** | Scheduled job fetches live HTML from all five URLs every run |
| **No ops server** | Runs on GitHub-hosted runners; no separate scheduler VM |
| **Audit trail** | Each run gets a timestamped directory under `data/corpus_runs/<run_id>/` |
| **Quality gate** | Pipeline fails if fetch, assembly, or Phase 1.5 validation fails |
| **Version history** | Successful runs are committed; older runs kept for rollback (7-day cleanup) |

### Schedule and triggers

```yaml
# Daily at 10:00 AM IST (04:30 UTC)
schedule:
  - cron: '30 4 * * *'

# Manual run for urgent source updates (Groww HTML changes, etc.)
workflow_dispatch:
  inputs:
    force_run: ...
```

- **Scheduled:** daily at **10:00 AM IST** (04:30 UTC) — ensures users get answers grounded in recently fetched AMC pages.
- **Manual:** trigger from **Actions → Automated Corpus Ingestion and Validation → Run workflow** when you need an immediate refresh.

### Pipeline executed each run

```text
1.1 Fetch (allowlist) → 1.2 Raw snapshots → 1.3 HTML→text
        → 1.4 Corpus assembly → 1.5 Semantic validation
```

| Step | Command / action |
|------|------------------|
| Ingest + assembly | `python3 -m phase1.ingestion.ingest_through_1_4` |
| Validation | `python3 -m phase1.ingestion.subphase_1_5_validation.run` |
| Verify | All 5 `clean.txt` files; `validation_report.json` with `validation_ok: true` |

On success, the workflow also updates **`config/corpus_manifest.json`** (`last_fetch_at`, `scheme_names_observed`) via Phase 1.4 assembly.

### Artifacts committed per run

Under `data/corpus_runs/<run_id>/` (raw HTML is **not** committed to save space):

- `clean.txt` (per source)
- `snapshot_meta.json`, `ingest_manifest.json`, `corpus.json`
- `validation_report.json`, `embedding_quality.json`, `handoff_checklist.json`
- `run_summary.json`

Phase 3 **“Last updated from sources”** footer uses `fetched_at_utc` from the latest successful run.

### Failure handling and rollback

- **Fetch or validation failure:** workflow exits non-zero; previous committed run remains the latest good corpus.
- **Rollback:** use an earlier `data/corpus_runs/<run_id>/` directory (runs older than 7 days are cleaned up automatically on success).
- **Notifications:** failure step logs to Actions; optional Slack/webhook can be added in the workflow.

### Local vs scheduled ingest

| Mode | When to use |
|------|-------------|
| **GitHub Actions (scheduled)** | Production freshness; daily automatic updates |
| **Manual local** | Development and debugging |

```bash
# Full local pipeline (same as CI)
python3 -m phase1.ingestion.ingest_through_1_5
```

### Downstream (Phase 2+)

After a successful scheduled ingest, **rebuild the Phase 2 index** from the latest run (documented in Phase 5 README). The chatbot should query the index built from the most recent `handoff_checklist.json` → `corpus_run_dir`.

---

## Cross-cutting concerns (all phases)

| Concern | Approach |
|--------|-----------|
| Source integrity | **Five fixed URLs only**; **daily GitHub Actions refresh**; version metadata per fetch |
| Advice avoidance | System prompts, refusal templates, no comparative language |
| Privacy | Stateless or minimal session; no PII fields in UI or logs |
| Transparency | One URL per answer; last-updated line from source metadata |
| Operational reliability | **GitHub Actions** scheduler (`.github/workflows/ingestion.yml`); validation gates; rollback via prior `corpus_runs/` |

---

## Mapping to success criteria

| Success criterion | Primary phases |
|-------------------|----------------|
| Accurate retrieval | 1–2 |
| Facts-only responses | 0, 3 |
| Valid citations | 2–3 |
| Refusal behavior | 0, 3 |
| Minimal UI | 4 |
| Reproducibility and clarity | 5 |

This phased plan aligns implementation order with risk: **corpus and policy first**, **retrieval second**, **generation and UI last**, **documentation and handoff** at the end.
