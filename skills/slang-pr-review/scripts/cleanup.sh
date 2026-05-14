#!/usr/bin/env bash
# Minimize + resolve prior `nv-slang-bot[bot]` reviews/threads/comments on the target PR.
# Called as a pre-step by compose-and-run.sh in --live-on-fork mode.
# Faithful port of claude-pr-review.yml lines 131–184 (GraphQL via `gh api graphql`).
#
# Usage: cleanup.sh <owner/repo> <pr_number> [<login>]
#   login defaults to "nv-slang-bot" — in GraphQL the [bot] suffix is stripped.
#
# Hard guard: refuses any non-szihs/* repo (safety rail mirrored from the workflow).

set -euo pipefail

REPO="${1:?usage: cleanup.sh owner/repo pr_number [login]}"
PR="${2:?pr number required}"
LOGIN="${3:-nv-slang-bot}"

[[ "$REPO" == szihs/* ]] || { echo "error: refusing to clean up non-szihs repo: $REPO" >&2; exit 1; }

OWNER="${REPO%%/*}"
NAME="${REPO#*/}"

echo ">>> cleanup: $REPO#$PR, matching author login = '$LOGIN'"

QUERY='query($owner: String!, $repo: String!, $pr: Int!) {
  repository(owner: $owner, name: $repo) {
    pullRequest(number: $pr) {
      reviews(last: 100) { nodes { id author { login } state } }
      reviewThreads(last: 100) {
        nodes {
          id
          isResolved
          comments(first: 1) { nodes { author { login } } }
        }
      }
      comments(last: 100) { nodes { id author { login } isMinimized } }
    }
  }
}'

RESULT=$(gh api graphql -f query="$QUERY" -F owner="$OWNER" -F repo="$NAME" -F pr="$PR")

MIN=0
RES=0

# 1. Minimize previous bot reviews (mark OUTDATED).
for ID in $(echo "$RESULT" | python3 -c "
import json,sys
d=json.load(sys.stdin)
pr=d['data']['repository']['pullRequest']
L='$LOGIN'
for r in pr['reviews']['nodes']:
    if r.get('author') and r['author'].get('login')==L:
        print(r['id'])
"); do
  gh api graphql -f query='mutation($id: ID!){ minimizeComment(input:{subjectId:$id, classifier:OUTDATED}){ minimizedComment{ isMinimized } } }' \
    -F id="$ID" >/dev/null 2>&1 && MIN=$((MIN+1)) || true
done

# 2. Resolve bot-authored unresolved review threads.
for TID in $(echo "$RESULT" | python3 -c "
import json,sys
d=json.load(sys.stdin)
pr=d['data']['repository']['pullRequest']
L='$LOGIN'
for t in pr['reviewThreads']['nodes']:
    if t['isResolved']: continue
    cs=t['comments']['nodes']
    if cs and cs[0].get('author') and cs[0]['author'].get('login')==L:
        print(t['id'])
"); do
  gh api graphql -f query='mutation($tid: ID!){ resolveReviewThread(input:{threadId:$tid}){ thread{ isResolved } } }' \
    -F tid="$TID" >/dev/null 2>&1 && RES=$((RES+1)) || true
done

# 3. Minimize bot issue-level comments (tracking / progress comments).
for CID in $(echo "$RESULT" | python3 -c "
import json,sys
d=json.load(sys.stdin)
pr=d['data']['repository']['pullRequest']
L='$LOGIN'
for c in pr['comments']['nodes']:
    if c['isMinimized']: continue
    if c.get('author') and c['author'].get('login')==L:
        print(c['id'])
"); do
  gh api graphql -f query='mutation($id: ID!){ minimizeComment(input:{subjectId:$id, classifier:OUTDATED}){ minimizedComment{ isMinimized } } }' \
    -F id="$CID" >/dev/null 2>&1 && MIN=$((MIN+1)) || true
done

echo ">>> cleanup: minimized $MIN reviews/comments, resolved $RES threads"
