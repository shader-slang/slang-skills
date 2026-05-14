#!/usr/bin/env bash
# Top-level entry for the slang-pr-review skill.
# Selects the input mode (pr/branch/patch), prepares the slang/ checkout
# accordingly, then delegates to repro.sh for the actual claude invocation.
#
# Usage:
#   compose-and-run.sh --mode pr     --pr <N>  --repo <owner/repo> [--live-on-fork] [--max-budget-usd $]
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
LIVE_ON_FORK=0
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
    --live-on-fork) LIVE_ON_FORK=1; shift ;;
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
    [ "$LIVE_ON_FORK" = "1" ] && { echo "error: --live-on-fork only valid in pr mode" >&2; exit 1; }
    ;;
  patch)
    [ -n "$PATCH_FILE" ] || { echo "error: --patch <path> required for patch mode" >&2; exit 1; }
    [ -f "$PATCH_FILE" ] || { echo "error: patch file not found: $PATCH_FILE" >&2; exit 1; }
    [ "$LIVE_ON_FORK" = "1" ] && { echo "error: --live-on-fork only valid in pr mode" >&2; exit 1; }
    ;;
  *)
    echo "error: --mode must be pr | branch | patch (got: $MODE)" >&2
    exit 1
    ;;
esac

# Live-on-fork hard guard — refuses any non-szihs/* repo.
if [ "$LIVE_ON_FORK" = "1" ]; then
  [[ "$REPO" == szihs/* ]] || {
    echo "error: --live-on-fork requires --repo szihs/* (got: $REPO). Refusing to post to non-fork repo." >&2
    exit 1
  }
  command -v "$HOME/.local/bin/mcp-server-github" >/dev/null \
    || { echo "error: mcp-server-github missing. Run install.sh." >&2; exit 1; }
fi

# Tooling sanity
command -v claude >/dev/null || { echo "error: claude CLI not in PATH. Run install.sh." >&2; exit 1; }
command -v gh     >/dev/null || { echo "error: gh CLI missing." >&2; exit 1; }

[ -f "$REPO_ROOT/REVIEW.md" ] \
  || { echo "error: $REPO_ROOT/REVIEW.md not found. Run install.sh." >&2; exit 1; }

# --- Mode-specific repo prep ----------------------------------------------

cd "$REPO_ROOT"

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

export MODE REPO PR_NUMBER BRANCH_REF BRANCH_BASE PATCH_FILE
export LIVE_ON_FORK MAX_BUDGET_USD MAX_TURNS MODEL
export REPO_ROOT RUN_DIR HERE SKILL_DIR

bash "$HERE/repro.sh"
RC=$?

# Patch-mode cleanup: roll back the temp branch.
if [ "$MODE" = "patch" ] && [ -n "${TEMP_BRANCH:-}" ]; then
  cd "$REPO_ROOT"
  git checkout -q origin/master >/dev/null 2>&1 || true
  git branch -D "$TEMP_BRANCH" >/dev/null 2>&1 || true
fi

exit "$RC"
