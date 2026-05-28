#!/usr/bin/env bash
#
# post-back.sh — orchestration wrapper around cleanup.sh + post-review.sh.
#
# This is what the wrapping workflow calls when it has decided to post a
# review back to GitHub. Splitting orchestration here keeps the workflow's
# Step 6 to a single invocation; the cleanup-then-post sequence lives in
# one place that's easier to amend later.
#
# Usage: post-back.sh <repo> <pr-number> <body-file> [bot-login]
#   repo:       owner/name
#   pr-number:  numeric
#   body-file:  path to the markdown body for the review
#   bot-login:  GraphQL author.login string (default: nv-slang-bot).
#               Cleanup minimizes/resolves only this bot's prior content.
#
# Exit codes:
#   0  — review posted (or both cleanup + post succeeded)
#   2  — bad inputs (missing body file, etc.)
#   3  — 403 from GitHub on post (token lacks pull_requests:write).
#        Caller should fall back to send_file only.
#   1  — other failure (network, malformed payload, ...). Caller should
#        log + return via send_file.
#
# Side-effects:
#   1. cleanup.sh: minimize prior bot reviews/comments + resolve threads
#   2. post-review.sh: POST COMMENT-state review + safety-net dismissal
#
# Cleanup is best-effort; post failure is fatal. If cleanup fails but post
# succeeds, that's still a successful run (cleanup is hygiene).
set -uo pipefail

REPO="${1:?repo required (owner/name)}"
PR="${2:?pr number required}"
BODY_FILE="${3:?body-file path required}"
BOT_LOGIN="${4:-nv-slang-bot}"

if [ ! -s "$BODY_FILE" ]; then
  echo "post-back.sh: body file $BODY_FILE is empty or missing — refusing to post" >&2
  exit 2
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# 1. Pre-cleanup. Best-effort — failures here don't block the post; the
#    new review just lands on top of any prior bot content. Cleanup runs
#    silently on success and prints a "minimized N, resolved M" line.
"$SCRIPT_DIR/cleanup.sh" "$REPO" "$PR" "$BOT_LOGIN" \
  || echo "post-back.sh: cleanup non-fatal — proceeding to post" >&2

# 2. Post review (COMMENT-state). post-review.sh exits 3 on 403 and
#    propagates other errors. We exit with the same code so callers can
#    distinguish 403 (graceful degrade) from other failures.
"$SCRIPT_DIR/post-review.sh" "$REPO" "$PR" "$BODY_FILE"
RC=$?

if [ "$RC" -eq 0 ]; then
  echo "post-back.sh: ok — $REPO#$PR (bot=$BOT_LOGIN)"
fi

exit "$RC"
