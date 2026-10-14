#!/usr/bin/env bash
# Top-level entry for the slang-pr-review skill.
# Selects the input mode (pr/branch/patch), prepares the slang/ checkout
# accordingly, then delegates to repro.sh for the actual claude invocation.
#
# Usage:
#   compose-and-run.sh --mode pr     --pr <N>  --repo <owner/repo> [--max-budget-usd $]
#   compose-and-run.sh --mode branch --branch <ref> --repo <owner/repo>
#   compose-and-run.sh --mode patch  --patch <path> [--base <ref>]

set -euo pipefail
# ~/.local/bin is the fallback install.sh uses when the environment ships no
# claude CLI; it goes last so the NanoClaw image's /pnpm/claude is the one run.
export PATH="$PATH:$HOME/.local/bin"

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HERE="$SKILL_DIR/scripts"
REPO_ROOT="${REPO_ROOT:-/workspace/agent/slang}"

MODE=""
PR_NUMBER=""
BRANCH_REF=""
BRANCH_BASE="origin/master"
PATCH_FILE=""
REPO=""
MAX_BUDGET_USD="${REPRO_PR_MAX_BUDGET_USD:-30}"
MAX_TURNS="${REPRO_PR_MAX_TURNS:-500}"
MODEL="${REPRO_PR_MODEL:-${ANTHROPIC_DEFAULT_OPUS_MODEL:-opus}}"

while (($#)); do
  case "$1" in
    --mode) MODE="$2"; shift 2 ;;
    --pr) PR_NUMBER="$2"; shift 2 ;;
    --branch) BRANCH_REF="$2"; shift 2 ;;
    --base) BRANCH_BASE="$2"; shift 2 ;;
    --patch) PATCH_FILE="$2"; shift 2 ;;
    --repo) REPO="$2"; shift 2 ;;
    --max-budget-usd) MAX_BUDGET_USD="$2"; shift 2 ;;
    --max-turns) MAX_TURNS="$2"; shift 2 ;;
    --model) MODEL="$2"; shift 2 ;;
    -h|--help) sed -n '2,12p' "$0"; exit 0 ;;
    *) echo "error: unknown flag $1" >&2; exit 1 ;;
  esac
done

# --- Validate inputs -------------------------------------------------------

[ -n "$MODE" ] || { echo "error: --mode pr|branch|patch required" >&2; exit 1; }

case "$MODE" in
  pr)
    [ -n "$PR_NUMBER" ] || { echo "error: --pr <N> required for pr mode" >&2; exit 1; }
    [ -n "$REPO" ] || { echo "error: --repo <owner/repo> required for pr mode" >&2; exit 1; }
    ;;
  branch)
    [ -n "$BRANCH_REF" ] || { echo "error: --branch <ref> required for branch mode" >&2; exit 1; }
    [ -n "$REPO" ] || { echo "error: --repo <owner/repo> required for branch mode" >&2; exit 1; }
    ;;
  patch)
    [ -n "$PATCH_FILE" ] || { echo "error: --patch <path> required for patch mode" >&2; exit 1; }
    [ -f "$PATCH_FILE" ] || { echo "error: patch file not found: $PATCH_FILE" >&2; exit 1; }
    ;;
  *)
    echo "error: --mode must be pr | branch | patch (got: $MODE)" >&2
    exit 1
    ;;
esac

# Tooling sanity
command -v claude >/dev/null || { echo "error: claude CLI not in PATH. Run install.sh." >&2; exit 1; }
command -v gh     >/dev/null || { echo "error: gh CLI missing." >&2; exit 1; }

[ -f "$REPO_ROOT/REVIEW.md" ] \
  || { echo "error: $REPO_ROOT/REVIEW.md not found. Run install.sh." >&2; exit 1; }

# --- Mode-specific repo prep ----------------------------------------------

cd "$REPO_ROOT"

# Diff-integrity: never let an artifact from a previous run survive into this
# one (a stale patch would be reviewed as this PR's). In pr mode prestage.sh
# rewrites all three artifacts below, like production's trusted pre-stage step;
# the other modes run with none.
rm -f "$REPO_ROOT/tmp/pr-diff.patch" "$REPO_ROOT/tmp/pr-files.txt" "$REPO_ROOT/tmp/context.json"

case "$MODE" in
  pr)
    # Production behavior: BASE branch (master) is checked out locally and the
    # PR diff is pre-staged under tmp/ before any model runs.
    git fetch --depth 50 origin master >/dev/null 2>&1 || true
    git checkout -q origin/master 2>/dev/null || true
    ;;
  branch)
    # Fetch the requested branch (potentially from a fork — REPO).
    BRANCH_OWNER="${REPO%%/*}"
    git remote get-url "$BRANCH_OWNER" >/dev/null 2>&1 \
      || git remote add "$BRANCH_OWNER" "https://github.com/$REPO.git"
    git fetch --depth 50 "$BRANCH_OWNER" "$BRANCH_REF" >/dev/null 2>&1
    git fetch --depth 50 origin master >/dev/null 2>&1 || true
    git checkout -q "$BRANCH_OWNER/$BRANCH_REF"
    ;;
  patch)
    # Apply patch onto a temp branch off origin/master.
    git fetch --depth 50 origin master >/dev/null 2>&1 || true
    TEMP_BRANCH="patch-review-$(date -u +%s)"
    git checkout -q -b "$TEMP_BRANCH" origin/master
    git apply --whitespace=nowarn "$PATCH_FILE" || {
      echo "error: patch did not apply cleanly" >&2
      git checkout -q origin/master
      git branch -D "$TEMP_BRANCH" >/dev/null 2>&1
      exit 1
    }
    git -c user.email=skill@nanoclaw -c user.name=skill commit -q -am "patch under review (temporary)"
    REPO="(local)"
    BRANCH_REF="$TEMP_BRANCH"
    BRANCH_BASE="origin/master"
    ;;
esac

# --- Run -----------------------------------------------------------------

TS="$(date -u +%Y%m%dT%H%M%SZ)"
RUN_DIR="$SKILL_DIR/transcripts/${MODE}-${TS}"
mkdir -p "$RUN_DIR"

# --- Pre-stage (pr mode) ---------------------------------------------------
# Write tmp/pr-diff.patch, tmp/pr-files.txt and tmp/context.json exactly as
# production's trusted "Pre-stage PR diff and context" step does, so the
# reviewers read the diff instead of fetching it themselves (the prompt tells
# them so). Field names in context.json (repo, pr, base_sha, head_sha,
# diff_sha256) match the contract REVIEW.md Step 1 verifies — keep them
# identical. Then verify the marker matches the requested PR before any
# reviewer is dispatched.
if [ "$MODE" = "pr" ]; then
  bash "$HERE/prestage.sh" "$REPO" "$PR_NUMBER" "$REPO_ROOT" "$RUN_DIR"

  # Verify the freshly written marker matches the requested PR before dispatch.
  read_marker() { python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))[sys.argv[2]])' "$1" "$2" 2>/dev/null || true; }
  MARK="$REPO_ROOT/tmp/context.json"
  [ -f "$MARK" ] || { echo "error: context marker $MARK was not written — aborting before review" >&2; exit 1; }
  if [ "$(read_marker "$MARK" repo)" != "$REPO" ] || [ "$(read_marker "$MARK" pr)" != "$PR_NUMBER" ]; then
    echo "error: context marker mismatch — refusing to dispatch reviewers against a mismatched diff" >&2
    echo "       marker=($(read_marker "$MARK" repo) #$(read_marker "$MARK" pr)) requested=($REPO #$PR_NUMBER)" >&2
    exit 1
  fi
fi

export MODE REPO PR_NUMBER BRANCH_REF BRANCH_BASE PATCH_FILE
export MAX_BUDGET_USD MAX_TURNS MODEL
export REPO_ROOT RUN_DIR HERE SKILL_DIR

# Capture the inner exit code without letting set -e skip the cleanup and the
# post-run guards below (a "successful" run that did no real work still needs
# to be caught and turned into a nonzero exit).
RC=0
bash "$HERE/repro.sh" || RC=$?

# Patch-mode cleanup: roll back the temp branch.
if [ "$MODE" = "patch" ] && [ -n "${TEMP_BRANCH:-}" ]; then
  cd "$REPO_ROOT"
  git checkout -q origin/master >/dev/null 2>&1 || true
  git branch -D "$TEMP_BRANCH" >/dev/null 2>&1 || true
fi

# --- Post-run reliability guards ------------------------------------------
# A run that did no real review work must never exit 0. Guards accumulate into
# GUARD_RC and, if any tripped, override the inner exit code.
GUARD_RC=0

# Diff-integrity net: the diff the reviewers read must be the one prestage.sh
# wrote for PR $PR_NUMBER. Compare the file's hash with the one recorded in
# tmp/context.json at pre-stage time (and kept as pr-diff.reference in the run
# dir); a rewritten, truncated or swapped diff fails LOUD. The hash is the
# right key — file lists would misreport deletions and renames.
if [ "$MODE" = "pr" ]; then
  staged="$(read_marker "$REPO_ROOT/tmp/context.json" diff_sha256)"
  now="$( { sha256sum "$REPO_ROOT/tmp/pr-diff.patch" 2>/dev/null \
            || shasum -a 256 "$REPO_ROOT/tmp/pr-diff.patch" 2>/dev/null; } | cut -d' ' -f1 || true)"
  if [ -z "$staged" ] || [ -z "$now" ] || [ "$staged" != "$now" ]; then
    echo "!!! INTEGRITY-FAIL: tmp/pr-diff.patch no longer matches the diff pre-staged for PR $PR_NUMBER — review targeted the WRONG diff" >&2
    printf 'pre-staged sha256: %s\nsha256 after the run: %s\nreference copy: %s/pr-diff.reference\n' \
      "${staged:-<none>}" "${now:-<missing file>}" "$RUN_DIR" > "$RUN_DIR/INTEGRITY-FAIL.txt"
    GUARD_RC=1
  fi
fi

# Zero-subagent guard: a review with no Task/Agent dispatch means no reviewers
# ran — the fake-clean incident where a run with zero subagents produced a
# 96-byte "review" and exited 0. Count dispatches in the script's own
# tool-uses.jsonl (deterministic one-JSON-object-per-line artifact).
DISPATCHES=0
[ -f "$RUN_DIR/tool-uses.jsonl" ] \
  && DISPATCHES="$(grep -cE '"name": "(Task|Agent)"' "$RUN_DIR/tool-uses.jsonl" || true)"
if [ "${DISPATCHES:-0}" -eq 0 ]; then
  echo "!!! REVIEW-GUARD FAIL: zero Task/Agent subagent dispatches — no reviewers ran" >&2
  GUARD_RC=1
fi

# Minimum-output guard: a truncated or empty final review is not a real review.
FINAL_SIZE=0
[ -f "$RUN_DIR/final-review.md" ] \
  && FINAL_SIZE="$(wc -c < "$RUN_DIR/final-review.md" | tr -d ' ')"
if [ "${FINAL_SIZE:-0}" -lt 500 ]; then
  echo "!!! REVIEW-GUARD FAIL: final review is ${FINAL_SIZE} bytes (<500) — no substantive review produced" >&2
  GUARD_RC=1
fi

# Infra-error guard: a surfaced transient error must not masquerade as a review.
if [ -f "$RUN_DIR/final-review.md" ] \
  && grep -qiE 'API Error|socket|rate.?limit' "$RUN_DIR/final-review.md"; then
  echo "!!! REVIEW-GUARD FAIL: final review looks like an infrastructure error, not a review" >&2
  GUARD_RC=1
fi

if [ "$GUARD_RC" -ne 0 ]; then
  exit "$GUARD_RC"
fi
exit "$RC"
