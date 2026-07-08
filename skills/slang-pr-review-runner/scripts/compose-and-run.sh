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
export PATH="$HOME/.local/bin:$PATH"

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

# Diff-integrity guard: drop any stale cross-run diff artifacts before the run.
# A leftover tmp/pr-diff.patch from a prior PR previously caused a wrong-PR
# review (PR #11455 reviewed as #11443): the model's sandboxed write to the
# file was denied, so it silently read the stale copy. Clearing them means the
# worst case is an empty read that falls back to a live `gh pr diff`, never a
# wrong diff. See docs/slang-skills-pr-diff-integrity-fix.
rm -f "$REPO_ROOT/tmp/pr-diff.patch" "$REPO_ROOT/tmp/pr-files.txt" "$REPO_ROOT/tmp/context.json"

case "$MODE" in
  pr)
    # Production behavior: BASE branch (master) is checked out locally.
    # The model uses gh pr diff to see the PR's actual changes.
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

# --- Diff-integrity marker (pr mode) --------------------------------------
# Record what the reviewers are about to review so a stale/wrong diff fails
# loud instead of silent. Field names (repo, pr, base_sha, head_sha,
# diff_sha256) match the context contract standardized across the GitHub
# Actions review frontend (see shader-slang/slang PR #11993's pre-stage step)
# — keep them identical. Then verify the marker matches the requested PR
# before any reviewer is dispatched.
if [ "$MODE" = "pr" ]; then
  case "$PR_NUMBER" in
    ''|*[!0-9]*) echo "error: --pr must be a positive integer (got: $PR_NUMBER)" >&2; exit 1 ;;
  esac
  mkdir -p "$REPO_ROOT/tmp"
  HEAD_SHA="$(gh pr view "$PR_NUMBER" -R "$REPO" --json headRefOid -q .headRefOid 2>/dev/null || true)"
  BASE_SHA="$(gh pr view "$PR_NUMBER" -R "$REPO" --json baseRefOid -q .baseRefOid 2>/dev/null || true)"
  [ -n "$HEAD_SHA" ] \
    || { echo "error: could not resolve head SHA for PR $PR_NUMBER in $REPO — refusing to review a phantom PR" >&2; exit 1; }
  gh pr diff "$PR_NUMBER" -R "$REPO" > "$RUN_DIR/pr-diff.reference" 2>/dev/null || true
  DIFF_SHA256="$( { sha256sum "$RUN_DIR/pr-diff.reference" 2>/dev/null \
                    || shasum -a 256 "$RUN_DIR/pr-diff.reference" 2>/dev/null; } | cut -d' ' -f1 || true)"
  python3 - "$REPO" "$PR_NUMBER" "$BASE_SHA" "$HEAD_SHA" "$DIFF_SHA256" > "$REPO_ROOT/tmp/context.json" <<'PY'
import json, sys
repo, pr, base, head, diff = sys.argv[1:6]
json.dump({"repo": repo, "pr": int(pr), "base_sha": base, "head_sha": head, "diff_sha256": diff}, sys.stdout)
sys.stdout.write("\n")
PY

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

# Diff-integrity net: if the model materialized tmp/pr-diff.patch, assert it
# actually describes PR $PR_NUMBER. A stale/wrong diff fails LOUD. If the file
# is absent the model reviewed via a live `gh pr diff` (the safe path) — skip.
if [ "$MODE" = "pr" ] && [ -f "$REPO_ROOT/tmp/pr-diff.patch" ]; then
  used="$(grep -oE '^\+\+\+ b/.+' "$REPO_ROOT/tmp/pr-diff.patch" 2>/dev/null | sed 's#^+++ b/##' | sort -u || true)"
  real="$(gh pr view "$PR_NUMBER" -R "$REPO" --json files -q '.files[].path' 2>/dev/null | sort -u || true)"
  if [ -n "$real" ] && [ "$used" != "$real" ]; then
    echo "!!! INTEGRITY-FAIL: reviewed diff != PR $PR_NUMBER files — review targeted the WRONG diff" >&2
    printf 'reviewed:\n%s\n\nactual PR files:\n%s\n' "$used" "$real" > "$RUN_DIR/INTEGRITY-FAIL.txt"
    GUARD_RC=1
  fi
fi

if [ "$GUARD_RC" -ne 0 ]; then
  exit "$GUARD_RC"
fi
exit "$RC"
