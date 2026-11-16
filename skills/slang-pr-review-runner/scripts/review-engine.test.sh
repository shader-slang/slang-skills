#!/usr/bin/env bash
# Tests for the inner-reviewer engine choice (review-engine.sh) and for the
# OpenCode path of compose-and-run.sh / repro.sh / opencode-review.py.
#
# Usage: bash scripts/review-engine.test.sh
#
# The end-to-end cases run compose-and-run.sh in patch mode against a throwaway
# checkout with stub `claude`, `opencode` and `gh` commands, so no model, no
# network and no GitHub access is involved. Each stub records how it was called;
# the assertions check which CLI ran and what it received. Exit 0 = all passed.
set -u

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PASS=0
FAIL=0

ok() { PASS=$((PASS + 1)); echo "  ok   $1"; }
bad() { FAIL=$((FAIL + 1)); echo "  FAIL $1"; }
# check <description> <command...>: passes when the command succeeds.
check() { local name="$1"; shift; if "$@"; then ok "$name"; else bad "$name"; fi; }
absent() { [ ! -e "$1" ]; }
has() { grep -q -- "$1" "$2"; }
hasline() { grep -qx -- "$1" "$2"; }
lacks() { ! grep -q -- "$1" "$2"; }
is() { [ "$1" = "$2" ]; }

# --- review_engine ------------------------------------------------------------

echo "review_engine:"
engine_for() {
  ( unset NANOCLAW_MODEL_WEIGHTS
    [ "$1" = "<unset>" ] || export NANOCLAW_MODEL_WEIGHTS="$1"
    . "$HERE/review-engine.sh"
    review_engine )
}
check "unset weights -> claude" is "$(engine_for "<unset>")" claude
check "weights=any -> claude" is "$(engine_for any)" claude
check "weights=open -> opencode" is "$(engine_for open)" opencode
check "only the exact value open selects opencode" is "$(engine_for OPEN)" claude

# --- fixture --------------------------------------------------------------------

T="$(mktemp -d "${TMPDIR:-/tmp}/review-engine-test.XXXXXX")"
trap 'rm -rf "$T"' EXIT
STUB="$T/stub"
mkdir -p "$STUB" "$T/home"

git init -q --bare "$T/origin.git"
git init -q "$T/slang"
(
  cd "$T/slang"
  mkdir -p .claude/agents .github
  printf '# Review protocol\n' > REVIEW.md
  printf '# Rules\n- @.github/copilot-instructions.md\n- @AGENTS.md\n- @~/.claude/user-only.md\n- `@notanimport`\n' > CLAUDE.md
  printf 'agents\n' > AGENTS.md
  printf 'copilot\n' > .github/copilot-instructions.md
  printf -- '---\nname: code-quality-reviewer\ndescription: Reviews code quality.\ntools: Glob, Grep, Read, mcp__deepwiki__ask_question\nmodel: sonnet\n---\n\nReview the diff.\n' \
    > .claude/agents/code-quality-reviewer.md
  printf 'one\n' > file.txt
  git add -A
  git -c user.email=t@t -c user.name=t commit -q -m init
  git branch -M master
  git remote add origin "$T/origin.git"
  git push -q origin master
  git fetch -q origin
)
printf -- '--- a/file.txt\n+++ b/file.txt\n@@ -1 +1,2 @@\n one\n+two\n' > "$T/change.patch"

cat > "$STUB/gh" <<'EOF'
#!/usr/bin/env bash
exit 0
EOF

cat > "$STUB/claude" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' "$@" > "$STUB_LOG/claude.args"
body="$(printf 'x%.0s' $(seq 1 600))"
echo '{"type":"assistant","message":{"content":[{"type":"tool_use","name":"Task","input":{"subagent_type":"code-quality-reviewer"}}]}}'
echo "{\"type\":\"assistant\",\"message\":{\"content\":[{\"type\":\"text\",\"text\":\"## Claude review\\n$body\"}]}}"
EOF

cat > "$STUB/opencode" <<'EOF'
#!/usr/bin/env bash
if [ "${1:-}" = "--version" ]; then echo 0.0.0-stub; exit 0; fi
printf '%s\n' "$@" > "$STUB_LOG/opencode.args"
printf '%s' "$OPENCODE_CONFIG_CONTENT" > "$STUB_LOG/opencode.config.json"
{
  echo "XDG_CONFIG_HOME=$XDG_CONFIG_HOME"
  echo "XDG_DATA_HOME=$XDG_DATA_HOME"
  echo "OPENCODE_DISABLE_PROJECT_CONFIG=${OPENCODE_DISABLE_PROJECT_CONFIG:-}"
  echo "OPENCODE_DISABLE_EXTERNAL_SKILLS=${OPENCODE_DISABLE_EXTERNAL_SKILLS:-}"
} > "$STUB_LOG/opencode.env"
body="$(printf 'y%.0s' $(seq 1 600))"
echo '{"type":"step_start","part":{"type":"step-start"}}'
echo '{"type":"tool_use","part":{"type":"tool","tool":"task","callID":"call_1","state":{"status":"completed","input":{"subagent_type":"code-quality-reviewer","prompt":"go"},"output":"<task_result>no findings</task_result>"}}}'
echo "{\"type\":\"text\",\"part\":{\"type\":\"text\",\"text\":\"## OpenCode review\\n$body\"}}"
echo '{"type":"step_finish","part":{"type":"step-finish","cost":0,"tokens":{"input":10,"output":5}}}'
EOF
chmod +x "$STUB"/*

# run_case <name> [VAR=value ...] -- [compose-and-run flags ...]
# Runs compose-and-run.sh in patch mode with a clean environment; the stubs log
# into $T/<name>/ and the run directory is $T/<name>/run.
run_case() {
  local name="$1"; shift
  local dir="$T/$name"
  mkdir -p "$dir"
  local vars=()
  while [ $# -gt 0 ] && [ "$1" != "--" ]; do vars+=("$1"); shift; done
  [ "${1:-}" = "--" ] && shift
  env -i HOME="$T/home" PATH="${CASE_PATH:-$STUB:/usr/bin:/bin}" STUB_LOG="$dir" \
    REPO_ROOT="$T/slang" REVIEW_RUN_DIR="$dir/run" ${vars[@]+"${vars[@]}"} \
    bash "$HERE/compose-and-run.sh" --mode patch --patch "$T/change.patch" "$@" \
    > "$dir/out.log" 2>&1
  echo $? > "$dir/rc"
}
rc_is() { [ "$(cat "$T/$1/rc")" = "$2" ]; }
# cfg <case> <python expression over c>: passes when the expression over the
# config the opencode stub received is true.
cfg() {
  python3 - "$T/$1/opencode.config.json" "$2" <<'PY'
import json, sys
c = json.load(open(sys.argv[1]))
sys.exit(0 if eval(sys.argv[2]) else 1)
PY
}
arg_after() { grep -A1 -x -- "$2" "$T/$1/opencode.args" | tail -1; }

OPEN_ENV="NANOCLAW_MODEL_WEIGHTS=open OPENCODE_PROVIDER=openai OPENCODE_MODEL=openai/nvidia/zai-org/glm-5.3 OPENCODE_SMALL_MODEL=openai/nvidia/zai-org/glm-5.3-flash OPENCODE_BASE_URL=https://inference.example/v1"

# --- closed group: claude, unchanged -------------------------------------------

echo "closed group:"
run_case closed ANTHROPIC_DEFAULT_OPUS_MODEL=claude-test-opus --
C="$T/closed"
check "exit 0" rc_is closed 0
check "claude ran" test -f "$C/claude.args"
check "opencode did not run" absent "$C/opencode.args"
check "claude got the Opus model" hasline claude-test-opus "$C/claude.args"
check "claude kept --setting-sources project" hasline --setting-sources "$C/claude.args"
check "final-review.md is the claude text" has "Claude review" "$C/run/final-review.md"

# --- open-weights group: opencode with the group's model ----------------------

echo "open-weights group:"
# shellcheck disable=SC2086
run_case open $OPEN_ENV 'OPENCODE_CONFIG_CONTENT={"coworker":true}' ANTHROPIC_DEFAULT_OPUS_MODEL=claude-test-opus --
O="$T/open"
check "exit 0" rc_is open 0
check "opencode ran" test -f "$O/opencode.args"
check "claude did not run" absent "$O/claude.args"
check "opencode run" is "$(head -1 "$O/opencode.args")" run
check "--pure" hasline --pure "$O/opencode.args"
check "--format json" is "$(arg_after open --format)" json
check "model is OPENCODE_MODEL" is "$(arg_after open --model)" openai/nvidia/zai-org/glm-5.3
check "runs in the checkout" is "$(arg_after open --dir)" "$T/slang"
check "no Claude model anywhere in the config" lacks claude-test-opus "$O/opencode.config.json"
check "the coworker config is replaced" cfg open "'coworker' not in c"
check "small model is the group small model" cfg open "c['small_model'] == 'openai/nvidia/zai-org/glm-5.3-flash'"
check "endpoint and placeholder key" cfg open "c['provider']['openai']['options'] == {'apiKey': 'nc-opencode-token-v1', 'baseURL': 'https://inference.example/v1'}"
check "openai-compatible transport" cfg open "c['provider']['openai']['npm'] == '@ai-sdk/openai-compatible'"
check "bash: git diff* allowed, other commands denied" cfg open "c['permission']['bash']['git diff*'] == 'allow' and c['permission']['bash']['*'] == 'deny'"
check "edit: only tmp/**" cfg open "c['permission']['edit'] == {'*': 'deny', 'tmp/**': 'allow'}"
check "deny is the default" cfg open "list(c['permission'].items())[0] == ('*', 'deny')"
check "deepwiki tool allowed" cfg open "c['permission']['deepwiki_ask_question'] == 'allow'"
check "no permission is ask" lacks '"ask"' "$O/opencode.config.json"
check "steps = max turns" cfg open "c['agent']['build']['steps'] == 500"
check "reviewer is a subagent" cfg open "c['agent']['code-quality-reviewer']['mode'] == 'subagent'"
check "reviewer keeps no model of its own" cfg open "'model' not in c['agent']['code-quality-reviewer']"
check "reviewer keeps its tool list" cfg open "c['agent']['code-quality-reviewer']['permission'] == {'*': 'deny', 'external_directory': 'allow', 'doom_loop': 'allow', 'question': 'deny', 'glob': 'allow', 'grep': 'allow', 'read': 'allow', 'list': 'allow', 'deepwiki_ask_question': 'allow'}"
check "instructions: CLAUDE.md and its imports" cfg open "[p.split('/')[-1] for p in c['instructions'][:3]] == ['CLAUDE.md', 'copilot-instructions.md', 'AGENTS.md']"
check "instructions: system-prompt append and engine notes" cfg open "[p.split('/')[-1] for p in c['instructions'][3:]] == ['system-prompt-append.txt', 'opencode-engine-notes.md']"
check "mcp: deepwiki as a remote server" cfg open "c['mcp']['deepwiki']['type'] == 'remote' and c['mcp']['deepwiki']['url'] == 'https://mcp.deepwiki.com/mcp'"
check "private config directory" hasline "XDG_CONFIG_HOME=$O/run/opencode/config" "$O/opencode.env"
check "private data directory" hasline "XDG_DATA_HOME=$O/run/opencode/data" "$O/opencode.env"
check "project config off" hasline OPENCODE_DISABLE_PROJECT_CONFIG=true "$O/opencode.env"
check "home-directory skills off" hasline OPENCODE_DISABLE_EXTERNAL_SKILLS=true "$O/opencode.env"
check "final-review.md is the opencode text" has "OpenCode review" "$O/run/final-review.md"
check "tool-uses.jsonl records the task dispatch" has '"name": "task"' "$O/run/tool-uses.jsonl"
check "subagent output preserved" has "no findings" "$O/run/subagents/call_1.output"
check "budget gap is logged" has "has no OpenCode equivalent" "$O/out.log"
python3 "$HERE/summarize.py" "$O/run" > "$O/summary.txt" 2>&1
check "summarize.py counts the OpenCode task call" has "1  task" "$O/summary.txt"

echo "open-weights group, detached:"
# shellcheck disable=SC2086
run_case detached $OPEN_ENV -- --detach
check "detach returns 0 at once" rc_is detached 0
bash "$HERE/wait-run.sh" "$T/detached/run" --timeout 60 --poll 1 > /dev/null 2>&1
check "wait-run.sh returns the run's exit code 0" is "$?" 0
check "detached run used opencode" test -f "$T/detached/opencode.args"
check "detached run did not use claude" absent "$T/detached/claude.args"

echo "open-weights group, refused inputs:"
# shellcheck disable=SC2086
run_case model-flag $OPEN_ENV -- --model opus
check "--model is refused" rc_is model-flag 1
check "--model: the error says why" has "not accepted in an open-weights group" "$T/model-flag/out.log"
check "--model: claude did not run" absent "$T/model-flag/claude.args"
check "--model: opencode did not run" absent "$T/model-flag/opencode.args"

if [ -n "$(PATH=/usr/bin:/bin command -v opencode)" ]; then
  echo "  skip missing-opencode case: /usr/bin or /bin has an opencode"
else
  mkdir -p "$T/stub-noopencode"
  cp "$STUB/gh" "$STUB/claude" "$T/stub-noopencode/"
  # shellcheck disable=SC2086
  CASE_PATH="$T/stub-noopencode:/usr/bin:/bin" run_case no-opencode $OPEN_ENV --
  check "missing opencode fails" rc_is no-opencode 1
  check "missing opencode: the error says why" has "needs the opencode CLI" "$T/no-opencode/out.log"
  check "missing opencode: claude is not used instead" absent "$T/no-opencode/claude.args"
fi

run_case no-model NANOCLAW_MODEL_WEIGHTS=open OPENCODE_PROVIDER=openai --
check "missing OPENCODE_MODEL fails" rc_is no-model 1
check "missing OPENCODE_MODEL: the error says why" has "OPENCODE_MODEL is not set" "$T/no-model/out.log"
check "missing OPENCODE_MODEL: claude did not run" absent "$T/no-model/claude.args"

echo "install.sh, open-weights group:"
# shellcheck disable=SC2086
env -i HOME="$T/home" PATH="$STUB:/usr/bin:/bin" STUB_LOG="$T" SLANG_REPO="$T/slang" $OPEN_ENV \
  bash "$HERE/install.sh" > "$T/install.log" 2>&1
check "install.sh succeeds" is "$?" 0
check "install.sh reports opencode" has "opencode: .*0.0.0-stub" "$T/install.log"
check "install.sh installs no claude" lacks "installing @anthropic-ai/claude-code" "$T/install.log"

echo
echo "review-engine.test.sh: $PASS passed, $FAIL failed"
if [ "$FAIL" -ne 0 ]; then
  for f in "$T"/*/out.log; do echo "--- $f"; tail -15 "$f"; done
  exit 1
fi
