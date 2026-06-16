#!/usr/bin/env bash
# Build static UI for Vercel. Production API: mutualfundfaq-ragbot-1.onrender.com
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
DIST="$ROOT/dist"

# Production URLs — wins over a misconfigured Vercel dashboard env var
if [[ -f "$ROOT/deploy.env" ]]; then
  # shellcheck disable=SC1091
  source "$ROOT/deploy.env"
fi
BASE="${API_BASE_URL:-https://mutualfundfaq-ragbot-1.onrender.com}"
BASE="${BASE%/}"

if [[ ! "$BASE" =~ ^https?://[a-zA-Z0-9.-]+ ]]; then
  echo "ERROR: API_BASE_URL must be a URL like https://mutualfundfaq-ragbot-1.onrender.com"
  echo "Got: ${BASE:0:80}..."
  exit 1
fi

rm -rf "$DIST"
mkdir -p "$DIST/css" "$DIST/js" "$DIST/data"

cp "$ROOT/index.html" "$DIST/"
cp "$ROOT/css/"*.css "$DIST/css/"
cp "$ROOT/js/"*.js "$DIST/js/"
cp "$ROOT/data/"*.json "$DIST/data/" 2>/dev/null || true

printf 'window.API_BASE = %s;\n' "$(node -pe "JSON.stringify('${BASE}'.replace(/\\/$/, ''))")" > "$DIST/config.js"
echo "Wrote dist/config.js with API_BASE_URL=${BASE}"

echo "Static UI build complete → dist/ ($(find "$DIST" -type f | wc -l | tr -d ' ') files)"
