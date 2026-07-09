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
#   MAX_BUDGET_USD  <float>
#   MAX_TURNS       <int>
#   MODEL           <model id>
#   REPO_ROOT       <path to slang checkout>
#   RUN_DIR         <output dir>            (already exists)
#   HERE            <skill scripts dir>
#   SKILL_DIR       <skill root>            (for prompt-templates and reference)

set -euo pipefail

: "${MODE:?MODE not set}"
# LIVE_ON_FORK was removed — this skill always returns final-review.md to
# the caller via send_file (no GitHub posting). The dry-run trailer + dry-run
# tool allowlist + dry-run MCP config are now the only path.
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

TRAILER='DO NOT call any GitHub-write tool. Skip Step 5 of REVIEW.md. After completing all reviewer dispatches and your filter pass, output the COMPLETE final review (review body + every inline comment with `file:line` headers) as plain markdown in your final assistant message. End the session after that markdown block. The harness writes that markdown to `final-review.md` and the calling workflow returns it to the requester via `send_file`.'

PROMPT_FILE="$RUN_DIR/prompt.txt"
cat > "$PROMPT_FILE" <<EOF
FIRST: Read the file \`REVIEW.md\` using the Read tool. It contains
your MANDATORY review protocol — template, tone rules, and subagent dispatch instructions.
You MUST follow every instruction in that file exactly. Do NOT skip reading it.

REPO: ${PROMPT_REPO}
PR NUMBER: ${PROMPT_PR}

IMPORTANT: The BASE branch (master) is checked out locally. You can read CLAUDE.md and any
existing source files locally to understand repo structure and surrounding code context.
The PR branch is NOT checked out — you are GIVEN the PR diff, pre-staged by a trusted
step: \`tmp/pr-diff.patch\` (full diff), \`tmp/pr-files.txt\` (changed paths), and
\`tmp/context.json\` (repo, pr, base_sha, head_sha, diff_sha256). Verify them per
REVIEW.md Step 1 and use them as-is; if any is missing or does not match this PR
number, regenerate all three freshly per Step 1 before proceeding. Use gh/GitHub MCP
tools only for metadata (comments, CI status), and do NOT assume local files reflect
the PR's changes.

NOTE: Any previous Claude reviews on this PR have been automatically minimized
and their threads resolved. You are posting a fresh, self-contained review.
Do NOT reference previous reviews — just review the PR as it currently stands.

${TRAILER}
EOF

SYSTEM_APPEND="$(cat "$SKILL_DIR/prompt-templates/system-prompt-append.txt")"

# --- Tool allowlist --------------------------------------------------------

# Allows the inner CLI to read the PR via gh, and (when the wrapping
# workflow gates it on a webhook trigger) call gh api / gh api graphql to
# minimize prior bot reviews and post the merged COMMENT-state review.
# This mirrors what production's claude-code-action does — see
# shader-slang/slang/.github/workflows/claude-pr-review.yml. The cleanup
# and post are typically done by the wrapping workflow's helper scripts
# (cleanup.sh, post-review.sh) rather than the inner CLI itself; the
# allowlist below is permissive enough for either path.
read -r -d '' ALLOWED <<'EOF' || true
Read,View,Glob,GlobTool,Grep,GrepTool,Agent,BatchTool,
Skill,Write(tmp/**),Edit(tmp/**),
Bash(sha256sum *),Bash(shasum *),
Bash(git diff*),Bash(git log*),Bash(git show*),Bash(git status*),
Bash(grep *),Bash(grep -*),
Bash(cat *),Bash(head *),Bash(tail *),
Bash(ls *),Bash(find *),Bash(wc *),
Bash(gh pr diff*),Bash(gh pr view*),Bash(gh pr list*),Bash(gh pr checks*),
Bash(gh api repos/*/pulls/*),Bash(gh api repos/*/issues/*),
Bash(gh api graphql*),
mcp__deepwiki__ask_question
EOF
MCP_CONFIG="$SKILL_DIR/prompt-templates/mcp.dryrun.json"
ALLOWED="$(echo "$ALLOWED" | tr -d '\n' | tr -s ' ' | sed 's/, /,/g')"

# --- Run claude ------------------------------------------------------------

echo ">>> repro.sh: pr=${PROMPT_PR} repo=${PROMPT_REPO} mode=${MODE}"
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
echo ">>> subagents:     $RUN_DIR/subagents/"
