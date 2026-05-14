#!/usr/bin/env bash
# The actual `claude` CLI invocation. Mirrors production byte-for-byte for the chosen mode.
# Called by compose-and-run.sh; not intended for direct use.
#
# Inputs (env vars set by compose-and-run.sh):
#   MODE            pr | branch | patch
#   REPO            <owner/repo>            (pr/branch only)
#   PR_NUMBER       <int>                   (pr only)
#   BRANCH_REF      <branch name>           (branch only)
#   BRANCH_BASE     <base ref>              (branch only — diff base)
#   PATCH_FILE      <path>                  (patch only)
#   LIVE_ON_FORK    1 | 0
#   MAX_BUDGET_USD  <float>
#   MAX_TURNS       <int>
#   MODEL           <model id>
#   REPO_ROOT       <path to slang checkout>
#   RUN_DIR         <output dir>            (already exists)
#   HERE            <skill scripts dir>
#   SKILL_DIR       <skill root>            (for prompt-templates and reference)

set -euo pipefail

: "${MODE:?MODE not set}"
: "${LIVE_ON_FORK:?LIVE_ON_FORK not set}"
: "${REPO_ROOT:?REPO_ROOT not set}"
: "${RUN_DIR:?RUN_DIR not set}"
: "${SKILL_DIR:?SKILL_DIR not set}"

# --- Construct user prompt -------------------------------------------------
# Templates live in $SKILL_DIR/prompt-templates/. They are byte-equivalent to
# what claude-code-action@v1 + claude-pr-review.yml send in production.

case "$MODE" in
  pr)
    : "${REPO:?}"
    : "${PR_NUMBER:?}"
    PROMPT_REPO="$REPO"
    PROMPT_PR="$PR_NUMBER"
    ;;
  branch)
    : "${REPO:?}"
    : "${BRANCH_REF:?}"
    PROMPT_REPO="$REPO"
    PROMPT_PR="(branch:$BRANCH_REF)"
    ;;
  patch)
    PROMPT_REPO="(local-patch)"
    PROMPT_PR="(patch:$(basename "$PATCH_FILE"))"
    ;;
esac

if [[ "$LIVE_ON_FORK" == "1" ]]; then
  TRAILER='LIVE-ON-FORK MODE: Posting is enabled against the szihs/* fork only. Follow REVIEW.md Step 5 to post ONE review via the GitHub MCP. Note: this harness exposes `create_pull_request_review` (single-shot with inline `comments: [...]`) instead of the 3-call pending-review trio. Put the review body + every inline comment into a single `create_pull_request_review` call with event="COMMENT". Never call APPROVE or REQUEST_CHANGES.'
else
  TRAILER='DRY RUN MODE: Do NOT call any GitHub-write tool. Skip Step 5 of REVIEW.md. After completing all reviewer dispatches and your filter pass, output the COMPLETE final review (review body + every inline comment with `file:line` headers) as plain markdown in your final assistant message. End the session after that markdown block.'
fi

PROMPT_FILE="$RUN_DIR/prompt.txt"
cat > "$PROMPT_FILE" <<EOF
FIRST: Read the file \`REVIEW.md\` using the Read tool. It contains
your MANDATORY review protocol — template, tone rules, and subagent dispatch instructions.
You MUST follow every instruction in that file exactly. Do NOT skip reading it.

REPO: ${PROMPT_REPO}
PR NUMBER: ${PROMPT_PR}

IMPORTANT: The BASE branch (master) is checked out locally. You can read CLAUDE.md and any
existing source files locally to understand repo structure and surrounding code context.
However, the PR branch is NOT checked out — to see what the PR actually changes, you MUST
use \`gh pr diff\` or GitHub MCP tools. Do NOT assume local files reflect the PR's changes.

NOTE: Any previous Claude reviews on this PR have been automatically minimized
and their threads resolved. You are posting a fresh, self-contained review.
Do NOT reference previous reviews — just review the PR as it currently stands.

${TRAILER}
EOF

SYSTEM_APPEND="$(cat "$SKILL_DIR/prompt-templates/system-prompt-append.txt")"

# --- Tool allowlist --------------------------------------------------------

read -r -d '' ALLOWED_DRYRUN <<'EOF' || true
Read,View,Glob,GlobTool,Grep,GrepTool,Agent,BatchTool,
Bash(git diff*),Bash(git log*),Bash(git show*),Bash(git status*),
Bash(grep *),Bash(grep -*),
Bash(cat *),Bash(head *),Bash(tail *),
Bash(ls *),Bash(find *),Bash(wc *),
Bash(gh pr diff*),Bash(gh pr view*),Bash(gh pr list*),Bash(gh pr checks*),
Bash(gh api repos/*/pulls/*),Bash(gh api repos/*/issues/*),
mcp__deepwiki__ask_question
EOF

read -r -d '' ALLOWED_LIVE <<'EOF' || true
Read,View,Glob,GlobTool,Grep,GrepTool,Agent,BatchTool,
Bash(git diff*),Bash(git log*),Bash(git show*),Bash(git status*),
Bash(grep *),Bash(grep -*),
Bash(cat *),Bash(head *),Bash(tail *),
Bash(ls *),Bash(find *),Bash(wc *),
Bash(gh pr diff*),Bash(gh pr view*),Bash(gh pr list*),Bash(gh pr checks*),
Bash(gh api repos/*/pulls/*),Bash(gh api repos/*/issues/*),
mcp__deepwiki__ask_question,
mcp__github__get_pull_request,
mcp__github__get_pull_request_files,
mcp__github__get_pull_request_comments,
mcp__github__get_pull_request_reviews,
mcp__github__get_pull_request_status,
mcp__github__get_issue,
mcp__github__create_pull_request_review,
mcp__github__add_issue_comment
EOF

if [[ "$LIVE_ON_FORK" == "1" ]]; then
  ALLOWED="$ALLOWED_LIVE"
  MCP_CONFIG="$SKILL_DIR/prompt-templates/mcp.live.json"
else
  ALLOWED="$ALLOWED_DRYRUN"
  MCP_CONFIG="$SKILL_DIR/prompt-templates/mcp.dryrun.json"
fi
ALLOWED="$(echo "$ALLOWED" | tr -d '\n' | tr -s ' ' | sed 's/, /,/g')"

# --- Live-on-fork pre-step: cleanup ---------------------------------------

if [[ "$LIVE_ON_FORK" == "1" ]]; then
  bash "$HERE/cleanup.sh" "$REPO" "$PR_NUMBER" "${REPRO_PR_CLEANUP_LOGIN:-nv-slang-bot}" 2>&1 \
    | tee "$RUN_DIR/cleanup.log"
fi

# --- Run claude ------------------------------------------------------------

echo ">>> repro.sh: pr=${PROMPT_PR} repo=${PROMPT_REPO} mode=${MODE} live=${LIVE_ON_FORK}"
echo ">>> REPO_ROOT=$REPO_ROOT"
echo ">>> mcp-config=$MCP_CONFIG"
echo ">>> output → $RUN_DIR"

cd "$REPO_ROOT"

claude \
  --print \
  --model "${MODEL:-${ANTHROPIC_DEFAULT_OPUS_MODEL:-opus}}" \
  --max-turns "${MAX_TURNS:-500}" \
  --max-budget-usd "${MAX_BUDGET_USD:-30}" \
  --setting-sources project \
  --mcp-config "$MCP_CONFIG" \
  --append-system-prompt "$SYSTEM_APPEND" \
  --allowed-tools "$ALLOWED" \
  --output-format stream-json \
  --verbose \
  --no-session-persistence \
  "$(cat "$PROMPT_FILE")" \
  | tee "$RUN_DIR/stream.jsonl"

# --- Post-run extraction --------------------------------------------------

# Final assistant text → final-review.md (markdown body in dry-run; success-summary in live)
python3 - <<PY > "$RUN_DIR/final-review.md"
import json
last=""
with open("$RUN_DIR/stream.jsonl") as f:
    for line in f:
        line=line.strip()
        if not line.startswith("{"): continue
        try: rec=json.loads(line)
        except: continue
        if rec.get("type")=="assistant":
            for b in rec.get("message",{}).get("content",[]):
                if b.get("type")=="text": last=b.get("text") or last
print(last)
PY

# Tool-uses flat list → tool-uses.jsonl
python3 - <<PY > "$RUN_DIR/tool-uses.jsonl"
import json
with open("$RUN_DIR/stream.jsonl") as f:
    for line in f:
        line=line.strip()
        if not line.startswith("{"): continue
        try: rec=json.loads(line)
        except: continue
        if rec.get("type")!="assistant": continue
        for b in rec.get("message",{}).get("content",[]):
            if b.get("type")=="tool_use":
                print(json.dumps({"name": b.get("name"), "input": b.get("input")}))
PY

# Live-on-fork: extract the create_pull_request_review input as posted-review.json
if [[ "$LIVE_ON_FORK" == "1" ]]; then
  python3 - <<PY > "$RUN_DIR/posted-review.json"
import json
posted=None
with open("$RUN_DIR/stream.jsonl") as f:
    for line in f:
        line=line.strip()
        if not line.startswith("{"): continue
        try: rec=json.loads(line)
        except: continue
        if rec.get("type")!="assistant": continue
        for b in rec.get("message",{}).get("content",[]):
            if b.get("type")=="tool_use" and "create_pull_request_review" in (b.get("name","")):
                posted = b.get("input")
                break
        if posted: break
print(json.dumps(posted or {}, indent=2))
PY
fi

# Subagent output preservation — copy task_notification.output_file's that still exist
mkdir -p "$RUN_DIR/subagents"
python3 - <<PY
import json, os, shutil
out_dir="$RUN_DIR/subagents"
with open("$RUN_DIR/stream.jsonl") as f:
    for line in f:
        line=line.strip()
        if not line.startswith("{"): continue
        try: rec=json.loads(line)
        except: continue
        if rec.get("type")=="system" and rec.get("subtype")=="task_notification":
            src = rec.get("output_file")
            tid = rec.get("task_id")
            if src and tid and os.path.exists(src):
                try: shutil.copy2(src, os.path.join(out_dir, f"{tid}.output"))
                except Exception as e: print(f"warn: could not preserve {tid}: {e}")
PY

echo
echo ">>> repro.sh: done"
echo ">>> stream:        $RUN_DIR/stream.jsonl"
echo ">>> final review:  $RUN_DIR/final-review.md"
echo ">>> tool calls:    $RUN_DIR/tool-uses.jsonl"
[[ "$LIVE_ON_FORK" == "1" ]] && echo ">>> posted review: $RUN_DIR/posted-review.json"
echo ">>> subagents:     $RUN_DIR/subagents/"
