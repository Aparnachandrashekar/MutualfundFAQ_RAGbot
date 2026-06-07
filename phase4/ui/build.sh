#!/usr/bin/env bash
# Injects Render API URL for Vercel (set API_BASE_URL in project env vars).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
BASE="${API_BASE_URL:-}"

if [[ -n "$BASE" ]]; then
  BASE="${BASE%/}"
  printf 'window.API_BASE = %s;\n' "$(node -pe "JSON.stringify(process.env.API_BASE_URL.replace(/\\/$/, ''))")" > "$ROOT/config.js"
  echo "Wrote config.js with API_BASE_URL=${BASE}"
else
  cat > "$ROOT/config.js" <<'EOF'
window.API_BASE = "";
EOF
  echo "WARNING: API_BASE_URL not set — set it in Vercel env vars to your Render URL."
fi

# static-build expects output in cwd when distDir is "."
echo "Static UI build complete."
