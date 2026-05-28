#!/usr/bin/env bash
#
# cleanup.sh — minimize/resolve prior bot reviews on a PR before posting a
# fresh review. Mirrors the "Clean up previous Claude reviews" step in
# shader-slang/slang/.github/workflows/claude-pr-review.yml.
#
# Targets only the bot identity passed in BOT_LOGIN (default: nv-slang-bot).
# Production auto-reviews (claude / github-actions) are deliberately not
# touched — coexistence is allowed; we only collapse our own prior runs.
#
# Usage: cleanup.sh <repo> <pr-number> [bot-login]
#   repo:       owner/name (e.g. shader-slang/slang)
#   pr-number:  numeric
#   bot-login:  GraphQL author.login string (default: nv-slang-bot)
#
# Side-effects (all best-effort, errors swallowed):
#   1. minimizeComment(OUTDATED) on every prior review BODY by this bot
#   2. resolveReviewThread on every unresolved review thread first-authored
#      by this bot (so prior inline comments don't pile up)
#   3. minimizeComment(OUTDATED) on every top-level issue comment by this
#      bot (tracking/progress comments)
#
# Requires: gh, jq. Token must have pull_requests:write on the target repo
# (granted via the App installation; OneCLI proxy injects automatically).
set -uo pipefail

REPO="${1:?repo required (owner/name)}"
PR="${2:?pr number required}"
BOT_LOGIN="${3:-nv-slang-bot}"

OWNER="${REPO%%/*}"
NAME="${REPO##*/}"

# Single GraphQL query returns everything we need (reviews, threads, comments).
# Avoids 3 round-trips and keeps cleanup atomic-ish.
QUERY=$(cat <<'GQL'
query($owner: String!, $name: String!, $pr: Int!) {
  repository(owner: $owner, name: $name) {
    pullRequest(number: $pr) {
      reviews(last: 100) {
        nodes { id author { login } state }
      }
      reviewThreads(last: 100) {
        nodes {
          id
          isResolved
          comments(first: 1) { nodes { author { login } } }
        }
      }
      comments(last: 100) {
        nodes { id author { login } isMinimized }
      }
    }
  }
}
GQL
)

RESULT=$(gh api graphql -F owner="$OWNER" -F name="$NAME" -F pr="$PR" -f query="$QUERY" 2>/dev/null)
if [ -z "$RESULT" ]; then
  echo "cleanup.sh: GraphQL query failed for $REPO#$PR — skipping cleanup" >&2
  exit 0
fi

MINIMIZED=0
RESOLVED=0

# --- 1. Minimize prior bot review bodies as OUTDATED ---
for id in $(echo "$RESULT" | jq -r --arg login "$BOT_LOGIN" \
              '.data.repository.pullRequest.reviews.nodes[]
               | select(.author.login == $login)
               | .id'); do
  if gh api graphql -F id="$id" -f query='
mutation($id: ID!) {
  minimizeComment(input: {subjectId: $id, classifier: OUTDATED}) {
    minimizedComment { isMinimized }
  }
}' >/dev/null 2>&1; then
    MINIMIZED=$((MINIMIZED + 1))
  fi
done

# --- 2. Resolve prior bot-authored review threads ---
for id in $(echo "$RESULT" | jq -r --arg login "$BOT_LOGIN" \
              '.data.repository.pullRequest.reviewThreads.nodes[]
               | select(.isResolved | not)
               | select((.comments.nodes[0].author.login // "") == $login)
               | .id'); do
  if gh api graphql -F id="$id" -f query='
mutation($id: ID!) {
  resolveReviewThread(input: {threadId: $id}) {
    thread { isResolved }
  }
}' >/dev/null 2>&1; then
    RESOLVED=$((RESOLVED + 1))
  fi
done

# --- 3. Minimize prior bot top-level issue comments ---
for id in $(echo "$RESULT" | jq -r --arg login "$BOT_LOGIN" \
              '.data.repository.pullRequest.comments.nodes[]
               | select(.isMinimized | not)
               | select(.author.login == $login)
               | .id'); do
  if gh api graphql -F id="$id" -f query='
mutation($id: ID!) {
  minimizeComment(input: {subjectId: $id, classifier: OUTDATED}) {
    minimizedComment { isMinimized }
  }
}' >/dev/null 2>&1; then
    MINIMIZED=$((MINIMIZED + 1))
  fi
done

echo "cleanup.sh: minimized $MINIMIZED reviews/comments, resolved $RESOLVED threads on $REPO#$PR (bot=$BOT_LOGIN)"
