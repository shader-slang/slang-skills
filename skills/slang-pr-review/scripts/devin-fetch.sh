#!/usr/bin/env bash
# Fetch Devin Review's analysis for a public GitHub PR via agent-browser.
# Output: <out>/devin-flags.md (extracted flag titles + Devin's narrative)
#
# Usage:
#   devin-fetch.sh --url <devin-review-url> --out <run-dir> [--poll-seconds 45] [--max-minutes 20]
#
# Returns 0 on success, 2 on auth-wall, 3 on timeout, 1 on any other error.
# The workflow treats failure as best-effort — Reviewer A still runs.

set -euo pipefail

URL=""
OUT=""
POLL=45
MAX_MIN=20

while (($#)); do
  case "$1" in
    --url) URL="$2"; shift 2 ;;
    --out) OUT="$2"; shift 2 ;;
    --poll-seconds) POLL="$2"; shift 2 ;;
    --max-minutes) MAX_MIN="$2"; shift 2 ;;
    *) echo "error: unknown flag $1" >&2; exit 1 ;;
  esac
done

[ -n "$URL" ] || { echo "error: --url required" >&2; exit 1; }
[ -n "$OUT" ] || { echo "error: --out required" >&2; exit 1; }
mkdir -p "$OUT"

agent-browser open "$URL"
sleep 5

# Detect auth wall before polling
if agent-browser eval 'document.body.innerText.toLowerCase().includes("sign in") || document.body.innerText.toLowerCase().includes("log in to view")' 2>/dev/null | grep -qi true; then
  echo "auth-wall: Devin requires login for this PR" > "$OUT/devin-error.txt"
  exit 2
fi

# Poll until "Analysis complete"
deadline=$(( $(date +%s) + MAX_MIN*60 ))
while [ "$(date +%s)" -lt "$deadline" ]; do
  if agent-browser eval 'document.body.innerText.includes("Analysis complete") && !document.body.innerText.includes("PR analysis in progress")' 2>/dev/null | grep -qi true; then
    break
  fi
  sleep "$POLL"
done

# Confirm complete (else timeout)
if ! agent-browser eval 'document.body.innerText.includes("Analysis complete")' 2>/dev/null | grep -qi true; then
  echo "timeout: Devin did not complete within ${MAX_MIN}m" > "$OUT/devin-error.txt"
  exit 3
fi

# Expand flags
agent-browser find text "Flags" click 2>/dev/null || true
sleep 2

# Extract narrative + flags
agent-browser eval 'document.body.innerText' 2>/dev/null > "$OUT/devin-page.txt"
agent-browser screenshot "$OUT/devin-screenshot.png" 2>/dev/null || true

# Build a clean markdown extract: AI analysis + flag list
python3 - "$OUT/devin-page.txt" > "$OUT/devin-flags.md" <<'PY'
import re, sys
text = open(sys.argv[1]).read()
# Heuristic: AI analysis = paragraph(s) before the Flags section
parts = re.split(r'\n\s*\d+\s*Flags?\s*\n', text, maxsplit=1)
analysis = parts[0].strip() if parts else text.strip()
flags = parts[1].strip() if len(parts) > 1 else ''
print('# Devin Review\n')
print('## AI Analysis\n')
print(analysis[:5000])
print('\n## Flags\n')
print(flags[:5000])
PY

echo ">>> devin-fetch: ${OUT}/devin-flags.md ($(wc -l < "$OUT/devin-flags.md") lines)"
