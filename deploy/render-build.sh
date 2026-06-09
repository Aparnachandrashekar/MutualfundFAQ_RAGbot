#!/usr/bin/env bash
# Render build — lite (BM25-only) or full hybrid depending on RETRIEVAL_MODE.
set -euxo pipefail

export PIP_DISABLE_PIP_VERSION_CHECK=1
export PIP_NO_CACHE_DIR=1
export HF_HOME="${HF_HOME:-/opt/render/project/src/.cache/huggingface}"

MODE="${RETRIEVAL_MODE:-bm25_only}"

echo "==> Upgrading pip..."
python -m pip install --upgrade pip

if [[ "${MODE}" == "bm25" || "${MODE}" == "bm25_only" ]]; then
  echo "==> Lite build (BM25-only, no PyTorch)..."
  python -m pip install -r deploy/requirements-api-lite.txt
else
  echo "==> Full hybrid build (CPU PyTorch + sentence-transformers)..."
  python -m pip install "torch==2.2.2+cpu" \
    --index-url https://download.pytorch.org/whl/cpu
  python -m pip install -r deploy/requirements-api.txt
  echo "==> Pre-caching embedding model..."
  python - <<'PY'
from sentence_transformers import SentenceTransformer
SentenceTransformer("BAAI/bge-small-en-v1.5")
print("Embedding model cached.")
PY
fi

echo "==> Render build finished successfully (mode=${MODE})."
