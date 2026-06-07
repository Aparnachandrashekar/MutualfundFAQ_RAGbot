#!/usr/bin/env bash
# Build static UI for Vercel (set API_BASE_URL to your Render service URL).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
DIST="$ROOT/dist"
BASE="${API_BASE_URL:-}"

rm -rf "$DIST"
mkdir -p "$DIST/css" "$DIST/js" "$DIST/data"

cp "$ROOT/index.html" "$DIST/"
cp "$ROOT/css/"*.css "$DIST/css/"
cp "$ROOT/js/"*.js "$DIST/js/"
cp "$ROOT/data/"*.json "$DIST/data/" 2>/dev/null || true

if [[ -n "$BASE" ]]; then
  BASE="${BASE%/}"
  printf 'window.API_BASE = %s;\n' "$(node -pe "JSON.stringify(process.env.API_BASE_URL.replace(/\\/$/, ''))")" > "$DIST/config.js"
  echo "Wrote dist/config.js with API_BASE_URL=${BASE}"
else
  cat > "$DIST/config.js" <<'EOF'
window.API_BASE = "";
EOF
  echo "WARNING: API_BASE_URL not set — set it in Vercel env vars to your Render URL."
fi

echo "Static UI build complete → dist/ ($(find "$DIST" -type f | wc -l | tr -d ' ') files)"
