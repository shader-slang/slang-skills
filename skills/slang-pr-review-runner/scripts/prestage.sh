#!/usr/bin/env bash
# Pre-stage the PR diff and context artifacts the reviewer reads, exactly as the
# trusted "Pre-stage PR diff and context" step of shader-slang/slang's
# claude-pr-review.yml does before any model runs:
#
#   tmp/pr-diff.patch   full `gh pr diff`
#   tmp/pr-files.txt    changed paths
#   tmp/context.json    {repo, pr, base_sha, head_sha, diff_sha256}
#
# REVIEW.md Step 1 verifies these against the PR number and aborts on a
# mismatch; the prompt tells the model to use them as-is. Writing all three
# fresh on every run means no artifact from a previous run survives into this
# one; the post-run guard in compose-and-run.sh checks the diff's hash afterwards.
#
# Usage: prestage.sh <owner/repo> <pr-number> <repo_root> [<copy-dir>]
#   base_sha is the checkout's HEAD (the base branch is checked out, like
#   production). With <copy-dir>, pr-diff.patch is also kept there as
#   pr-diff.reference for the run's transcript directory.
set -euo pipefail

REPO="${1:?usage: prestage.sh <owner/repo> <pr-number> <repo_root> [<copy-dir>]}"
PR_NUMBER="${2:?missing pr-number}"
REPO_ROOT="${3:?missing repo_root}"
COPY_DIR="${4:-}"

case "$PR_NUMBER" in
  ''|*[!0-9]*) echo "error: pr-number must be a positive integer (got: $PR_NUMBER)" >&2; exit 1 ;;
esac

HEAD_SHA="$(gh pr view "$PR_NUMBER" -R "$REPO" --json headRefOid -q .headRefOid 2>/dev/null || true)"
[ -n "$HEAD_SHA" ] \
  || { echo "error: could not resolve head SHA for PR $PR_NUMBER in $REPO — refusing to review a phantom PR" >&2; exit 1; }
BASE_SHA="$(git -C "$REPO_ROOT" rev-parse HEAD)"

mkdir -p "$REPO_ROOT/tmp"
gh pr diff "$PR_NUMBER" -R "$REPO" > "$REPO_ROOT/tmp/pr-diff.patch"
[ -s "$REPO_ROOT/tmp/pr-diff.patch" ] || { echo "error: pre-staged diff for PR $PR_NUMBER is empty" >&2; exit 1; }
gh pr view "$PR_NUMBER" -R "$REPO" --json files -q '.files[].path' > "$REPO_ROOT/tmp/pr-files.txt"

DIFF_SHA256="$( { sha256sum "$REPO_ROOT/tmp/pr-diff.patch" 2>/dev/null \
                  || shasum -a 256 "$REPO_ROOT/tmp/pr-diff.patch"; } | cut -d' ' -f1)"

python3 - "$REPO" "$PR_NUMBER" "$BASE_SHA" "$HEAD_SHA" "$DIFF_SHA256" > "$REPO_ROOT/tmp/context.json" <<'PY'
import json, sys
repo, pr, base, head, diff = sys.argv[1:6]
json.dump({"repo": repo, "pr": int(pr), "base_sha": base, "head_sha": head, "diff_sha256": diff}, sys.stdout)
sys.stdout.write("\n")
PY

if [ -n "$COPY_DIR" ]; then
  mkdir -p "$COPY_DIR"
  cp "$REPO_ROOT/tmp/pr-diff.patch" "$COPY_DIR/pr-diff.reference"
fi

echo "Pre-staged review artifacts:"
cat "$REPO_ROOT/tmp/context.json"
