#!/usr/bin/env bash
# Local smoke test mirroring Render startup (run from repo root).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PORT="${PORT:-8765}"
BASE="http://127.0.0.1:${PORT}"

export PHASE2_DIR="${PHASE2_DIR:-data/phase2_results}"
export SERVE_UI="${SERVE_UI:-false}"
export USE_LLM="${USE_LLM:-true}"

if [[ -z "${GROQ_API_KEY:-}" ]] && [[ -f .env ]]; then
  GROQ_API_KEY="$(python3 - <<'PY'
from pathlib import Path
for line in Path(".env").read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    key, _, val = line.partition("=")
    if key.strip() == "GROQ_API_KEY":
        print(val.strip().strip('"').strip("'"))
        break
PY
)"
  export GROQ_API_KEY
fi

echo "==> Checking phase2 index..."
test -f "${PHASE2_DIR}/retrieval/retrieval_config.json"

echo "==> Starting uvicorn on port ${PORT}..."
python3 -m uvicorn phase3.api.server:app --host 127.0.0.1 --port "${PORT}" &
PID=$!
trap 'kill ${PID} 2>/dev/null || true' EXIT

for _ in $(seq 1 30); do
  if curl -sf "${BASE}/health" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

echo "==> GET /health"
curl -sf "${BASE}/health" | python3 -m json.tool

echo "==> POST /query (loads retriever on first request — may take 30s)"
curl -sf -X POST "${BASE}/query" \
  -H "Content-Type: application/json" \
  -d '{"query":"What is the AUM of SBI Gold Fund?"}' | python3 -m json.tool

echo "==> Smoke test passed."
