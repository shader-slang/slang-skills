#!/usr/bin/env bash
#
# post-review.sh — post the merged review back to GitHub as a COMMENT-state
# review, with optional inline comments. Always uses event=COMMENT — never
# APPROVE or REQUEST_CHANGES (matches production's policy in
# shader-slang/slang/.github/workflows/claude-pr-review.yml).
#
# Usage: post-review.sh <repo> <pr-number> <body-file> [inline-comments-json]
#   repo:                  owner/name
#   pr-number:             numeric
#   body-file:             path to the markdown body for the review
#   inline-comments-json:  optional path to a file containing a JSON array
#                          of {path, line, body, side?, start_line?, start_side?}
#                          for inline per-line comments
#
# Behavior:
#   - On 403 (token lacks pull_requests:write on this repo): logs and exits
#     non-zero. The wrapping workflow falls back to send_file only.
#   - On any other failure: logs the error body and exits non-zero.
#   - Always followed by a safety-net pass that dismisses any APPROVED or
#     CHANGES_REQUESTED reviews from the bot — production's belt-and-
#     suspenders pattern.
#
# Requires: gh, jq. Token must have pull_requests:write.
set -uo pipefail

REPO="${1:?repo required (owner/name)}"
PR="${2:?pr number required}"
BODY_FILE="${3:?body-file path required}"
INLINE_FILE="${4:-}"
BOT_LOGIN="${BOT_LOGIN:-nv-slang-bot}"

if [ ! -s "$BODY_FILE" ]; then
  echo "post-review.sh: body file $BODY_FILE is empty or missing — refusing to post" >&2
  exit 2
fi

# Build the request payload. event=COMMENT is hard-coded; the inner CLI
# does not pick the state.
if [ -n "$INLINE_FILE" ] && [ -s "$INLINE_FILE" ]; then
  PAYLOAD=$(jq -n \
    --rawfile body "$BODY_FILE" \
    --slurpfile comments "$INLINE_FILE" \
    '{event: "COMMENT", body: $body, comments: $comments[0]}')
else
  PAYLOAD=$(jq -n \
    --rawfile body "$BODY_FILE" \
    '{event: "COMMENT", body: $body}')
fi

# Post via REST. Capture both stdout and the exit code; gh prints non-2xx
# bodies to stderr.
RESPONSE_FILE=$(mktemp)
trap 'rm -f "$RESPONSE_FILE"' EXIT

if echo "$PAYLOAD" | gh api "repos/$REPO/pulls/$PR/reviews" --method POST --input - >"$RESPONSE_FILE" 2>&1; then
  REVIEW_ID=$(jq -r '.id // empty' "$RESPONSE_FILE")
  REVIEW_URL=$(jq -r '.html_url // empty' "$RESPONSE_FILE")
  echo "post-review.sh: posted review id=$REVIEW_ID url=$REVIEW_URL"
else
  STATUS=$?
  # Detect 403 from gh's error format
  if grep -q "Resource not accessible by integration\|403" "$RESPONSE_FILE"; then
    echo "post-review.sh: 403 — bot token lacks pull_requests:write on $REPO. Skipping post; review will be returned via send_file only." >&2
    exit 3
  fi
  echo "post-review.sh: post failed (exit $STATUS):" >&2
  cat "$RESPONSE_FILE" >&2
  exit "$STATUS"
fi

# --- Safety net: dismiss any APPROVED / CHANGES_REQUESTED reviews from
# the bot. The CLI is instructed to use COMMENT only, but prompt-level
# constraints aren't mechanically enforced. This step guarantees no bot
# review can affect merge eligibility (matches production's pattern).
DISMISSED=0
for r in $(gh api "repos/$REPO/pulls/$PR/reviews" \
            --jq ".[] | select(.user.login==\"${BOT_LOGIN}[bot]\" and (.state==\"APPROVED\" or .state==\"CHANGES_REQUESTED\")) | .id" 2>/dev/null); do
  if gh api -X PUT "repos/$REPO/pulls/$PR/reviews/$r/dismissals" \
       -f message="Bot reviews must be COMMENT-state only; auto-dismissed by post-review.sh." >/dev/null 2>&1; then
    DISMISSED=$((DISMISSED + 1))
  fi
done

if [ "$DISMISSED" -gt 0 ]; then
  echo "post-review.sh: safety-net dismissed $DISMISSED non-COMMENT bot reviews on $REPO#$PR"
fi
