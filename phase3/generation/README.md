# Phase 3 — Generation, formatting, and guardrails

Implements answer generation per [PhaseWiseArchitecture.md](../../PhaseWiseArchitecture.md) §3.

## Response policy

| Scenario | Citation | Footer | Educational link |
|----------|----------|--------|------------------|
| Grounded factual answer | One corpus URL | `Last updated from sources: <date>` | — |
| Unknown / no evidence | **None** | **None** | **None** |
| Personal information | **None** | **None** | **None** |
| Advisory / comparison | — | — | One AMFI/SEBI link |

## HTTP API (backend for Phase 4 UI)

Start the server (serves API **and** Phase 4 UI at `/`):

```bash
pip install -r requirements.txt
python3 -m phase3.run_server
```

Open [http://localhost:8000](http://localhost:8000) for the chat UI.

Endpoints:

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Retriever/LLM readiness |
| POST | `/query` | Submit a question (`{"query": "..."}`) |
| GET | `/` | Service info and disclaimer |

Example:

```bash
curl -s http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"query": "What is the AUM of Unifi Mutual Fund?"}' | python3 -m json.tool
```

Response fields:

- `response` — answer or refusal text (max 3 sentences)
- `citation` — one corpus URL when grounded, else empty
- `footer` — `Last updated from sources: <date>` when cited, else empty
- `educational_link` — AMFI/SEBI link for advisory/comparison refusals only

## Run pipeline (CLI)

```bash
python3 -m phase3.run_phase3 \
  --phase2-dir data/phase2_results \
  --output data/phase3_results/phase3_pipeline_report.json \
  --test-compliance
```

Single query:

```bash
python3 -m phase3.generation.answer_generator \
  --query "What is the NAV of Choice Mutual Fund?" \
  --retrieval-index data/phase2_results/retrieval
```

Optional Groq LLM:

```bash
# 1. Create your local env file from the template
cp .env.example .env

# 2. Edit .env and set GROQ_API_KEY (get one at https://console.groq.com/keys)

# 3. Run with Groq enabled
python3 -m phase3.run_phase3 --phase2-dir data/phase2_results --use-llm

# Optional: override model in .env or via CLI
python3 -m phase3.run_phase3 --phase2-dir data/phase2_results --use-llm --groq-model llama-3.1-8b-instant
```

`.env` is gitignored — never commit it.

## Modules

| File | Role |
|------|------|
| `config.py` | Evidence thresholds, allowed URLs, API settings |
| `intent_classifier.py` | Route factual vs advisory vs personal-info queries |
| `guardrails.py` | Citation policy, refusal templates, privacy checks |
| `answer_generator.py` | Evidence gate + answer extraction |
| `query_service.py` | Orchestrates retrieval + generation (API + CLI) |
| `run_pipeline.py` | Batch CLI orchestrator |
| `../api/server.py` | FastAPI `/query` and `/health` endpoints |

## Outputs

```
data/phase3_results/
└── phase3_pipeline_report.json
```
