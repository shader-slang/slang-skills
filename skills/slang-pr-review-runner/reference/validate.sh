#!/usr/bin/env bash
# Validate that this skill's prompt-templates and repro.sh ALLOWED list match
# what the production claude-pr-review.yml + claude-code-action@v1 actually send.
#
# Compares 5 extracts (Side A, from a known-good production run log) against
# 5 corresponding extracts (Side B, from this skill's vendored sources):
#
#   1. User prompt
#   2. System-prompt append
#   3. Allowed-tools list
#   4. Model id
#   5. MCP server set
#
# A 5/5 byte-match means the skill is in sync with production. Any failure
# means upstream drifted; see reference/README.md for the update procedure.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$HERE/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# Locate the most recent production run log under reference/runs/.
LOG_FILE="$(ls -t "$HERE"/runs/run-*.log 2>/dev/null | head -1 || true)"
if [ -z "$LOG_FILE" ]; then
  echo "error: no run log found under $HERE/runs/. Drop a production claude-pr-review.yml run log to validate against." >&2
  exit 1
fi
echo ">>> validating against: $LOG_FILE"

# --- Side A: extract from production log -----------------------------------

# A1: user prompt (the FIRST: ... block written to claude-prompt.txt)
python3 <<PY > "$TMP/A_user_prompt.txt"
import re, sys
text = open("$LOG_FILE").read()
m = re.search(r"FIRST:[\s\S]+?Do NOT reference previous reviews — just review the PR as it currently stands\.", text)
if m:
    # Substitute REPO and PR_NUMBER placeholders so the comparison is structural.
    body = m.group(0)
    body = re.sub(r"REPO: [\w\-/]+", "REPO: \${REPO}", body)
    body = re.sub(r"PR NUMBER: \d+", "PR NUMBER: \${PR_NUMBER}", body)
    print(body)
PY

# A2: --system-prompt argument
grep -oP '(?<=--system-prompt ")[^"]+' "$LOG_FILE" | head -1 > "$TMP/A_sys_append.txt"

# A3: allowedTools list (from the SDK options JSON the action passes)
python3 <<PY > "$TMP/A_tools.txt"
import re, json
text = open("$LOG_FILE").read()
m = re.search(r'"allowedTools":\s*\[([^\]]+)\]', text)
if m:
    raw = m.group(1)
    items = [s.strip().strip('"') for s in raw.split(',') if s.strip()]
    print(",".join(items))
PY

# A4: model id
grep -oP '(?<="model": ")aws/anthropic/[^"]+' "$LOG_FILE" | head -1 > "$TMP/A_model.txt"

# A5: MCP servers (names only, in declaration order)
python3 <<PY > "$TMP/A_mcp.txt"
import re, json
text = open("$LOG_FILE").read()
m = re.search(r'"mcp_servers":\s*(\[[^\]]+\])', text)
if m:
    try:
        servers = json.loads(m.group(1))
        print(",".join(s.get("name","?") for s in servers))
    except Exception:
        pass
PY

# --- Side B: extract from this skill's sources ----------------------------

# B1: user prompt template (substitute placeholders to compare structure)
PROMPT_TEMPLATE="$SKILL_DIR/prompt-templates/user-prompt.template"
if [ ! -f "$PROMPT_TEMPLATE" ]; then
  # repro.sh embeds the prompt inline; reconstruct the equivalent template here.
  cat > "$TMP/B_user_prompt.txt" <<'EOF'
FIRST: Read the file `REVIEW.md` using the Read tool. It contains
your MANDATORY review protocol — template, tone rules, and subagent dispatch instructions.
You MUST follow every instruction in that file exactly. Do NOT skip reading it.

REPO: ${REPO}
PR NUMBER: ${PR_NUMBER}

IMPORTANT: The BASE branch (master) is checked out locally. You can read CLAUDE.md and any
existing source files locally to understand repo structure and surrounding code context.
However, the PR branch is NOT checked out — to see what the PR actually changes, you MUST
use `gh pr diff` or GitHub MCP tools. Do NOT assume local files reflect the PR's changes.

NOTE: Any previous Claude reviews on this PR have been automatically minimized
and their threads resolved. You are posting a fresh, self-contained review.
Do NOT reference previous reviews — just review the PR as it currently stands.
EOF
else
  cp "$PROMPT_TEMPLATE" "$TMP/B_user_prompt.txt"
fi

# B2: system-prompt append (single file, no substitutions)
cp "$SKILL_DIR/prompt-templates/system-prompt-append.txt" "$TMP/B_sys_append.txt"
# Strip trailing newline for byte-exact comparison
truncate -s "$(($(wc -c <"$TMP/B_sys_append.txt") - 1))" "$TMP/B_sys_append.txt"

# B3: allowed-tools list (extract ALLOWED_DRYRUN from repro.sh)
python3 <<PY > "$TMP/B_tools.txt"
import re
text = open("$SKILL_DIR/scripts/repro.sh").read()
m = re.search(r"ALLOWED_DRYRUN <<'EOF' \|\| true\n([\s\S]+?)\nEOF", text)
if m:
    raw = m.group(1)
    # Normalise to comma-separated single line, no whitespace
    items = [tok for tok in raw.replace("\n",",").split(",") if tok.strip()]
    print(",".join(t.strip() for t in items))
PY

# B4: model id (default model in repro.sh / compose-and-run.sh — env-derived)
echo "${ANTHROPIC_DEFAULT_OPUS_MODEL:-aws/anthropic/bedrock-claude-opus-4-7[1m]}" > "$TMP/B_model.txt"

# B5: MCP servers (from mcp.dryrun.json)
python3 <<PY > "$TMP/B_mcp.txt"
import json
cfg = json.load(open("$SKILL_DIR/prompt-templates/mcp.dryrun.json"))
print(",".join(cfg.get("mcpServers", {}).keys()))
PY

# --- Diff ---------------------------------------------------------------

PASS=0
FAIL=0
for k in user_prompt sys_append tools model mcp; do
  if diff -q "$TMP/A_${k}.txt" "$TMP/B_${k}.txt" >/dev/null 2>&1; then
    echo "  ✅ ${k}: byte-match"
    PASS=$((PASS+1))
  else
    echo "  ❌ ${k}: drift detected"
    diff -u "$TMP/A_${k}.txt" "$TMP/B_${k}.txt" | head -30 || true
    FAIL=$((FAIL+1))
  fi
done

echo
echo ">>> validate.sh: $PASS/5 byte-match, $FAIL drifted"
[ "$FAIL" -eq 0 ]
