#!/usr/bin/env bash
# Validate that this skill still mirrors what shader-slang/slang's
# claude-pr-review.yml (through its composite claude-code-runner action) and
# anthropics/claude-code-action send to the inner Claude CLI.
#
# Side A is the newest reference/runs/run-*.log: a production run log with the
# `review<TAB>UNKNOWN STEP<TAB><timestamp>` prefixes stripped (see the lock file
# for how to capture one). Side B is this skill: scripts/repro.sh and
# prompt-templates/.
#
# Five checks:
#   1. user prompt     byte-exact, with the REPO / PR NUMBER values replaced by
#                      placeholders on both sides
#   2. system append   byte-exact (production's --append-system-prompt vs
#                      prompt-templates/system-prompt-append.txt)
#   3. model           byte-exact against $ANTHROPIC_DEFAULT_OPUS_MODEL when set,
#                      else the `model=` line of claude-code-action.lock
#   4. allowed tools   production's list minus the GitHub MCP tools (we read and
#                      post through gh, never mcp-server-github) plus
#                      Bash(gh api graphql*) must equal repro.sh's ALLOWED list:
#                      the two documented divergences and nothing else
#   5. MCP servers     the server names in production's mcp-config input must
#                      equal prompt-templates/mcp.dryrun.json's
#
# Exit 0 only when all five pass. A failure names the field and prints the diff;
# see README.md for the update procedure.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$HERE/.." && pwd)"

LOG_FILE="$(ls -t "$HERE"/runs/run-*.log 2>/dev/null | head -1 || true)"
if [ -z "$LOG_FILE" ]; then
  echo "error: no run log under $HERE/runs/. Capture a production claude-pr-review.yml run log first (see claude-code-action.lock)." >&2
  exit 1
fi
echo ">>> validating against: $LOG_FILE"

python3 - "$LOG_FILE" "$SKILL_DIR" "${ANTHROPIC_DEFAULT_OPUS_MODEL:-}" <<'PY'
import json, re, sys

log_path, skill_dir, env_model = sys.argv[1:4]
log = open(log_path, encoding="utf-8", errors="replace").read()
lines = log.splitlines()

def fail(msg):
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(2)

# --- Side A: production run log -------------------------------------------

# A1: the `prompt:` input of the first `with:` block. The log prints the first
# line as `  prompt: FIRST: ...` and the rest of the multi-line value raw, up to
# the next input (`  custom-instructions:`).
a_prompt = None
for i, ln in enumerate(lines):
    if ln.startswith("  prompt: "):
        buf = [ln[len("  prompt: "):]]
        for nxt in lines[i + 1:]:
            if re.match(r"^  [a-z-]+: ", nxt) or re.match(r"^  [a-z-]+:$", nxt):
                break
            buf.append(nxt)
        a_prompt = "\n".join(buf).rstrip()
        break
if a_prompt is None:
    fail("could not find the `prompt:` input in the run log")
a_prompt = re.sub(r"REPO: \S+", "REPO: ${REPO}", a_prompt)
a_prompt = re.sub(r"PR NUMBER: \S+", "PR NUMBER: ${PR_NUMBER}", a_prompt)

# A2: the --append-system-prompt value from claude_args (one line, no inner
# double quotes — the composite action validates that).
m = re.search(r'--append-system-prompt "([^"\n]*)"', log)
if not m:
    fail("could not find --append-system-prompt in the run log")
a_append = m.group(1)

# A3 + A4: the SDK options the action logs right before running Claude.
m = re.search(r'SDK options: \{(.*?)\n\}', log, re.S)
if not m:
    fail("could not find the `SDK options:` block in the run log")
sdk = m.group(1)
mm = re.search(r'"allowedTools": \[(.*?)\]', sdk, re.S)
if not mm:
    fail("could not find allowedTools in the SDK options")
a_tools = re.findall(r'"([^"]+)"', mm.group(1))
mm = re.search(r'"model": "([^"]+)"', sdk)
if not mm:
    fail("could not find model in the SDK options")
a_model = mm.group(1)

# A5: server names in the `mcp-config:` input (deepwiki today). The GitHub and
# inline-comment servers the action injects by itself are not in this input.
a_mcp = None
for i, ln in enumerate(lines):
    if ln.startswith("  mcp-config: "):
        buf = [ln[len("  mcp-config: "):]]
        for nxt in lines[i + 1:]:
            buf.append(nxt)
            if nxt == "}":
                break
        try:
            a_mcp = sorted(json.loads("\n".join(buf)).get("mcpServers", {}).keys())
        except json.JSONDecodeError as e:
            fail(f"mcp-config input is not JSON: {e}")
        break
if a_mcp is None:
    fail("could not find the `mcp-config:` input in the run log")

# --- Side B: this skill -------------------------------------------------------

repro = open(f"{skill_dir}/scripts/repro.sh", encoding="utf-8").read()

# B1: the user-prompt heredoc in repro.sh, minus the skill's own trailer.
m = re.search(r'cat > "\$PROMPT_FILE" <<EOF\n(.*?)\nEOF\n', repro, re.S)
if not m:
    fail("could not find the PROMPT_FILE heredoc in scripts/repro.sh")
b_prompt = re.sub(r"\n*\$\{TRAILER\}\s*$", "", m.group(1))
b_prompt = b_prompt.replace("${PROMPT_REPO}", "${REPO}").replace("${PROMPT_PR}", "${PR_NUMBER}")
b_prompt = b_prompt.replace("\\`", "`").rstrip()

# B2: the system-prompt append template.
b_append = open(f"{skill_dir}/prompt-templates/system-prompt-append.txt", encoding="utf-8").read().rstrip("\n")

# B3: repro.sh's ALLOWED heredoc.
m = re.search(r"read -r -d '' ALLOWED <<'EOF' \|\| true\n(.*?)\nEOF\n", repro, re.S)
if not m:
    fail("could not find the ALLOWED heredoc in scripts/repro.sh")
b_tools = [t.strip() for t in m.group(1).replace("\n", ",").split(",") if t.strip()]

# B4: the model the skill runs by default — the container's
# ANTHROPIC_DEFAULT_OPUS_MODEL, recorded in the lock for validation off-box.
b_model = env_model
if not b_model:
    for ln in open(f"{skill_dir}/reference/claude-code-action.lock", encoding="utf-8"):
        if ln.startswith("model="):
            b_model = ln.split("=", 1)[1].strip()
if not b_model:
    fail("no ANTHROPIC_DEFAULT_OPUS_MODEL in the environment and no model= line in the lock")

# B5: the dry-run MCP config's server names.
b_mcp = sorted(json.load(open(f"{skill_dir}/prompt-templates/mcp.dryrun.json")).get("mcpServers", {}).keys())

# --- Compare ----------------------------------------------------------------

import difflib

results = []

def check(name, ok, detail=""):
    results.append(ok)
    print(f"  {'✅' if ok else '❌'} {name}: {'match' if ok else 'drift detected'}")
    if not ok and detail:
        print(detail)

def udiff(a, b, la, lb):
    return "".join(difflib.unified_diff(a.splitlines(True), b.splitlines(True), la, lb))[:4000]

check("user_prompt", a_prompt == b_prompt, udiff(a_prompt, b_prompt, "production", "repro.sh"))
check("sys_append", a_append == b_append, udiff(a_append, b_append, "production", "system-prompt-append.txt"))
check("model", a_model == b_model, f"    production: {a_model}\n    skill:      {b_model}")

# Documented divergences: no GitHub MCP server here (gh does the reads and the
# wrapping workflow's post-review.sh does the posting), and gh api graphql is
# allowed so the workflow's cleanup helper can run in the same session.
expected = {t for t in a_tools if not t.startswith(("mcp__github__", "mcp__github_inline_comment__"))}
expected.add("Bash(gh api graphql*)")
ours = set(b_tools)
missing = sorted(expected - ours)
extra = sorted(ours - expected)
detail = ""
if missing:
    detail += "    in production but not in repro.sh: " + ", ".join(missing) + "\n"
if extra:
    detail += "    in repro.sh but not in production: " + ", ".join(extra) + "\n"
check("allowed_tools", not missing and not extra, detail.rstrip())

check("mcp_servers", a_mcp == b_mcp, f"    production: {a_mcp}\n    skill:      {b_mcp}")

passed = sum(results)
print()
print(f">>> validate.sh: {passed}/5 match, {5 - passed} drifted")
sys.exit(0 if passed == 5 else 1)
PY
