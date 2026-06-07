#!/usr/bin/env bash
# Render build — CPU-only wheels, no source compiles. Target: ~8–12 min.
set -euxo pipefail

export PIP_DISABLE_PIP_VERSION_CHECK=1
export PIP_NO_CACHE_DIR=1
export HF_HOME="${HF_HOME:-/opt/render/project/src/.cache/huggingface}"

echo "==> Upgrading pip..."
python -m pip install --upgrade pip

echo "==> Installing CPU-only PyTorch (prebuilt wheel)..."
python -m pip install "torch==2.2.2+cpu" \
  --index-url https://download.pytorch.org/whl/cpu

echo "==> Installing API dependencies..."
python -m pip install -r deploy/requirements-api.txt

echo "==> Pre-caching embedding model (BAAI/bge-small-en-v1.5)..."
python - <<'PY'
from sentence_transformers import SentenceTransformer
SentenceTransformer("BAAI/bge-small-en-v1.5")
print("Embedding model cached.")
PY

echo "==> Render build finished successfully."
