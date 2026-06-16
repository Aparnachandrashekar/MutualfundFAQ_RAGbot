# Render deployment checklist

Use this when the dashboard was created manually (not from Blueprint). Settings must match [render.yaml](../render.yaml).

## Build & Deploy

| Setting | Value |
|---------|--------|
| **Branch** | `main` |
| **Root Directory** | *(empty — repo root)* |
| **Python Version** | `3.11.9` |
| **Build Command** | `bash deploy/render-build.sh` |
| **Start Command** | `uvicorn phase3.api.server:app --host 0.0.0.0 --port $PORT` |
| **Health Check Path** | `/health` |

## Environment variables

| Variable | Value |
|----------|--------|
| `PYTHON_VERSION` | `3.11.9` |
| `MISE_PYTHON_GITHUB_ATTESTATIONS` | `false` |
| `GROQ_API_KEY` | *(your Groq key)* |
| `USE_LLM` | `true` |
| `PHASE2_DIR` | `data/phase2_results` |
| `SERVE_UI` | `false` |
| `HF_HOME` | `/opt/render/project/src/.cache/huggingface` |
| `OMP_NUM_THREADS` | `1` |
| `RETRIEVAL_MODE` | `bm25_only` |

**Memory:** Starter (512MB) requires `RETRIEVAL_MODE=bm25_only` (lite build, no PyTorch). For full hybrid retrieval, upgrade to **Standard (2GB)** and set `RETRIEVAL_MODE=hybrid`.

## After changing settings

1. **Manual Deploy → Clear build cache & deploy**
2. Build log should end with: `==> Render build finished successfully.`
3. Service should go **Live** within ~2 min (lazy retriever — model loads on first query)
4. Verify:
   ```bash
   curl https://mutualfundfaq-ragbot-1.onrender.com/health
   curl -X POST https://mutualfundfaq-ragbot-1.onrender.com/query \
     -H "Content-Type: application/json" \
     -d '{"query":"What is the AUM of SBI Gold Fund?"}'
   ```

**Production URLs:** API `https://mutualfundfaq-ragbot-1.onrender.com` · UI `https://mutualfund-faq-ra-gbot.vercel.app`

## If build fails

| Log | Fix |
|-----|-----|
| `requirements.txt` not found | Build command must be `bash deploy/render-build.sh` |
| `blis` / `spacy` compile errors | You are installing full deps — use API requirements only |
| `cp314` in logs | Set Python **3.11.9** |

## If deploy never goes Live

| Log | Fix |
|-----|-----|
| `Killed` / exit 137 | Upgrade to **Standard (2GB)** — first `/query` loads PyTorch |
| Health check timeout | Confirm `/health` returns 200 before querying |

## Local smoke test

```bash
bash scripts/render-smoke-test.sh
```
