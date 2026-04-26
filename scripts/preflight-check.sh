#!/usr/bin/env bash
# Run before every `git push`. Exits non-zero if anything looks
# like a secret made it past .gitignore.
set -euo pipefail

cd "$(dirname "$0")/.."

fail=0

echo "[1/4] Looking for committed *.live files…"
if git ls-files 2>/dev/null | grep -E '\.live$|\.bak$|pihole-FTL\.db$|eve\.json$|teleporter.*\.tar\.gz$' ; then
    echo "  !! Files above are committed but should be gitignored."
    fail=1
fi

echo "[2/4] Looking for non-empty pwhash / totp_secret in tracked files…"
if git ls-files 2>/dev/null | xargs -I{} grep -lE '(pwhash|app_pwhash|totp_secret)\s*=\s*"[^"]+[A-Za-z0-9+/]' {} 2>/dev/null | grep -vE 'preflight-check\.sh|SECURITY\.md|\.example$'; then
    echo "  !! Above files contain a non-empty secret value. Redact before commit."
    fail=1
fi

echo "[3/4] Looking for a real Grafana / Pi-hole password in .env…"
if git ls-files 2>/dev/null | grep -E '(^|/)\.env$'; then
    echo "  !! monitoring/.env is tracked. Move it out of git."
    fail=1
fi

echo "[4/4] Looking for high-entropy strings in tracked text files…"
# Catch base64-ish blobs > 40 chars that aren't in known safe places.
if git ls-files 2>/dev/null | xargs -I{} grep -EHn '[A-Za-z0-9+/]{60,}={0,2}' {} 2>/dev/null \
    | grep -vE 'preflight-check\.sh|SECURITY\.md|\.json$|grafana/dashboards|README'; then
    echo "  !! High-entropy strings above. Inspect manually."
    fail=1
fi

if [ "$fail" -eq 0 ]; then
    echo
    echo "OK: no secrets found in tracked files."
else
    echo
    echo "FAIL: address the issues above before pushing."
    exit 1
fi
