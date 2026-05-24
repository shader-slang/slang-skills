---
name: slang-pr-create
description: Create and publish a GitHub pull request for Slang work, defaulting to a draft PR against shader-slang/slang and its default branch unless the user specifies another repository. Automatically use whenever asked to open, create, publish, or prepare a PR targeting any shader-slang/* repository, even if the user does not explicitly name this skill. Handles WSL environments that require Windows-hosted tools unless --wsl is requested.
argument-hint: "[--repo owner/repo-or-url] [--no-draft] [--wsl]"
allowed-tools: Bash Read Write Edit Grep Glob
required-capabilities: shell git github-cli file-read
---

# Slang PR Create

Create a focused GitHub pull request from the current branch. Default to
`shader-slang/slang`; if the user specifies a repo, use that repo instead.
Use this skill for any request to create, open, publish, or prepare a PR
targeting a `shader-slang/*` repository, even when the user does not explicitly
invoke `/slang-pr-create`.

**Usage**: `/slang-pr-create [--repo owner/repo-or-url] [--no-draft] [--wsl]`

PRs are created as drafts by default. Use `--no-draft` only when the PR should
be ready for review immediately. Created PRs are assigned to `@me` by default.
After creating a draft PR, request CodeRabbit review by commenting
`@coderabbitai review`. If the target repository is under `shader-slang/`, also
post `/ci all` to trigger CI.

`--wsl` means "use native WSL tools" when running inside WSL. Without it,
require Windows-hosted `.exe` tools such as `gh.exe`. If they are missing, stop
and tell the user to install the Windows tools or rerun with `--wsl`.

## Preconditions

- GitHub CLI (`gh` or `gh.exe`) is installed and authenticated.
- The current directory is a git worktree for the branch to publish.
- The branch has committed changes intended for the PR.

## Select Tools

Before running any `git` or `gh` command, detect WSL and choose tools. When the
agent is running under WSL, require `.exe` tools by default because GitHub
authentication and browser login are often configured on the Windows side. Do
not silently fall back to native WSL tools in this mode. If the user passes
`--wsl`, explicitly use native WSL tools instead.

```bash
ARGS="${ARGUMENTS:-}"
USE_WSL_TOOLS=false
DRAFT=true
if printf '%s\n' "$ARGS" | grep -Eq '(^|[[:space:]])--wsl([[:space:]]|$)'; then
  USE_WSL_TOOLS=true
  ARGS="$(printf '%s\n' "$ARGS" | sed -E 's/(^|[[:space:]])--wsl([[:space:]]|$)/ /; s/^[[:space:]]+//; s/[[:space:]]+$//')"
fi
if printf '%s\n' "$ARGS" | grep -Eq '(^|[[:space:]])--no-draft([[:space:]]|$)'; then
  DRAFT=false
  ARGS="$(printf '%s\n' "$ARGS" | sed -E 's/(^|[[:space:]])--no-draft([[:space:]]|$)/ /; s/^[[:space:]]+//; s/[[:space:]]+$//')"
fi

is_wsl() {
  [ -n "${WSL_DISTRO_NAME:-}" ] || grep -qi microsoft /proc/version 2>/dev/null
}

choose_tool() {
  tool="$1"
  if is_wsl && [ "$USE_WSL_TOOLS" = false ]; then
    if command -v "${tool}.exe" >/dev/null 2>&1; then
      printf '%s.exe\n' "$tool"
      return 0
    fi
    printf 'Missing Windows-hosted tool: %s.exe\n' "$tool" >&2
    printf 'Install it on Windows or rerun with --wsl to use native WSL %s.\n' "$tool" >&2
    return 1
  fi

  if command -v "$tool" >/dev/null 2>&1; then
    printf '%s\n' "$tool"
    return 0
  fi
  printf 'Missing native tool: %s\n' "$tool" >&2
  return 1
}

GIT="$(choose_tool git)" || exit 1
GH="$(choose_tool gh)" || exit 1
```

Use `$GIT` and `$GH` in all subsequent shell examples. Strip `\r` from command
substitution output because Windows `.exe` tools may print CRLF:

```bash
clean_line() { tr -d '\r'; }
```

Write the PR body outside the tracked worktree, then pass a Windows path from
`wslpath -w` when `$GH` ends in `.exe`:

```bash
BODY_FILE="$("$GIT" rev-parse --git-path slang-pr-body.md | clean_line)"
BODY_FILE_ARG="$BODY_FILE"
if is_wsl && [ "${GH%.exe}" != "$GH" ] && command -v wslpath >/dev/null 2>&1; then
  BODY_FILE_ARG="$(wslpath -w "$BODY_FILE")"
fi
```

## Resolve Inputs

Use the repository from the user request when provided. Accept `--repo
owner/repo`, `--repo https://github.com/owner/repo`, a bare positional
`owner/repo`, or a GitHub URL. If omitted, use:

```bash
REPO="shader-slang/slang"
```

Always query the target repository's default branch instead of assuming `master`
or `main`:

```bash
REPO_NAME_WITH_OWNER="$("$GH" repo view "$REPO" --json nameWithOwner --jq .nameWithOwner | clean_line)"
BASE="$("$GH" repo view "$REPO" --json defaultBranchRef --jq .defaultBranchRef.name | clean_line)"
BRANCH="$("$GIT" branch --show-current | clean_line)"
```

Try to determine the full issue references that the PR is intended to fix
before creating the PR. Closing references must use `owner/repo#123`, not just
`#123`.

First ask GitHub whether the current branch is already linked to one or more
issue development branches. `gh issue develop --list` works once an issue
number is known; to discover issues from the current branch, query the linked
branch metadata:

```bash
OWNER="${REPO_NAME_WITH_OWNER%/*}"
NAME="${REPO_NAME_WITH_OWNER#*/}"
mapfile -t LINKED_ISSUE_REFS < <("$GH" api graphql --paginate --slurp \
  -F owner="$OWNER" \
  -F name="$NAME" \
  -f query='query($owner: String!, $name: String!, $endCursor: String) {
    repository(owner: $owner, name: $name) {
      issues(first: 100, states: OPEN, after: $endCursor) {
        nodes {
          number
          repository { nameWithOwner }
          linkedBranches(first: 20) {
            nodes { ref { name repository { nameWithOwner } } }
          }
        }
        pageInfo { hasNextPage endCursor }
      }
    }
  }' | jq -r --arg branch "$BRANCH" '
    [.[].data.repository.issues.nodes[]
      | select(any(.linkedBranches.nodes[]?; .ref.name == $branch))
      | "\(.repository.nameWithOwner)#\(.number)"]
    | unique
    | .[]
  ')
```

This uses `gh api --slurp` with `--paginate` so `gh` wraps paginated GraphQL
responses in one JSON array before `jq` processes them.

If `jq` is unavailable, run the same GraphQL query and inspect the JSON output
manually for `linkedBranches` entries whose `ref.name` equals `$BRANCH`.

If this returns one or more issue references, include all of the references
that the PR fixes. If it returns none, use any full issue references explicitly
provided by the user. If only issue numbers are provided or inferred from clear
local evidence such as the branch name, commit message, or existing task
context, combine each issue number with `$REPO_NAME_WITH_OWNER`. If any issue
belongs to a different repository, use that issue's `owner/repo` instead.

Do not stop PR creation only because issue references cannot be inferred. Use
only confidently determined issue references, skip ambiguous or unavailable
ones, and omit closing lines entirely if no issue reference is known.

PowerShell / `gh.exe` equivalent:

```powershell
$repo = "shader-slang/slang"
$repoNameWithOwner = gh.exe repo view $repo --json nameWithOwner --jq ".nameWithOwner"
$base = gh.exe repo view $repo --json defaultBranchRef --jq ".defaultBranchRef.name"
$branch = git branch --show-current
$owner, $name = $repoNameWithOwner -split '/', 2
$query = @'
query($owner: String!, $name: String!, $endCursor: String) {
  repository(owner: $owner, name: $name) {
    issues(first: 100, states: OPEN, after: $endCursor) {
      nodes {
        number
        repository { nameWithOwner }
        linkedBranches(first: 20) {
          nodes { ref { name repository { nameWithOwner } } }
        }
      }
      pageInfo { hasNextPage endCursor }
    }
  }
}
'@
$pages = gh.exe api graphql --paginate --slurp `
  -F "owner=$owner" `
  -F "name=$name" `
  -f "query=$query" | ConvertFrom-Json
$linkedIssueRefs = @()
foreach ($page in $pages) {
  foreach ($issue in $page.data.repository.issues.nodes) {
    if ($issue.linkedBranches.nodes | Where-Object { $_.ref -and $_.ref.name -eq $branch }) {
      $linkedIssueRefs += "$($issue.repository.nameWithOwner)#$($issue.number)"
    }
  }
}
$linkedIssueRefs = $linkedIssueRefs | Sort-Object -Unique
```

## Required Safety Check

Before pushing or creating a PR, run:

```bash
"$GIT" status --short
```

If there is any output, **stop and clarify with the user before continuing**.
Show the changed and untracked files, then ask how to proceed. Do not commit,
stash, discard, push, or create the PR until the user chooses.

Offer these options:

1. **Commit all changes**: ask for a commit message, then run
   `"$GIT" add -A && "$GIT" commit -m "<message>"`.
2. **Commit only staged changes**: only if staged files exist; ask for a commit
   message, then run `"$GIT" commit -m "<message>"`.
3. **Stash changes**: run `"$GIT" stash push -m "slang-pr-create stash"` and
   create the PR from the current committed HEAD.
4. **Abort**: stop so the user can handle the worktree manually.

## Create The PR

Check basic state:

```bash
"$GH" auth status
"$GIT" status --short
"$GIT" remote -v
"$GIT" branch --show-current
"$GH" repo view "$REPO" --json nameWithOwner,defaultBranchRef,url
```

Do not create a PR from the default branch. If `BRANCH` is empty or equals
`BASE`, stop and ask the user to create or switch to a topic branch.

Fetch the target default branch and verify the branch has commits for the PR:

```bash
"$GIT" fetch "https://github.com/$REPO.git" "$BASE"
"$GIT" log --oneline FETCH_HEAD..HEAD
```

If there are no commits ahead of the target default branch, stop and report that
there is nothing committed to open as a PR.

Push the branch if needed:

```bash
PUSH_REMOTE="$("$GIT" config --get "branch.$BRANCH.remote" | clean_line || true)"
if [ -z "$PUSH_REMOTE" ]; then
  while IFS= read -r remote; do
    [ -z "$remote" ] && continue
    if "$GIT" remote get-url --push "$remote" >/dev/null 2>&1; then
      PUSH_REMOTE="$remote"
      break
    fi
  done < <("$GIT" remote | clean_line)
fi
if [ -z "$PUSH_REMOTE" ]; then
  echo "Could not determine a push remote. Ask before adding a remote or changing push destinations."
  exit 1
fi
"$GIT" push -u "$PUSH_REMOTE" HEAD
```

Prepare a concise PR body in `$BODY_FILE`. Prefer this structure:

```markdown
## Summary
- ...

## Test Plan
- ...
```

Use the exact tests or checks that were actually run. If no validation was run,
state that clearly in the Test Plan.

When one or more fixed issue references are known, append one
`Fixes shader-slang/slang#123`-style line per fixed issue, and do not duplicate
issue references. Do not include placeholder closing text. If no issue
reference is known, omit `Fixes` lines and continue creating the PR.

For `shader-slang/slang`, label the PR as `pr: non-breaking` by default unless
the change is intentionally breaking. For any other repo, only pass a label if
the repository has the label or the user explicitly requested one.

Create the PR:

```bash
LABEL_ARGS=()
if [ "$REPO" = "shader-slang/slang" ]; then
  LABEL_ARGS=(--label "pr: non-breaking")
fi
DRAFT_ARGS=()
if [ "$DRAFT" = true ]; then
  DRAFT_ARGS=(--draft)
fi

request_coderabbit_review_if_draft() {
  pr_ref="$1"
  if [ "$DRAFT" = true ]; then
    "$GH" pr comment "$pr_ref" --body '@coderabbitai review'
  fi
}

trigger_shader_slang_ci_if_needed() {
  pr_ref="$1"
  repo_name_with_owner="$REPO"
  repo_name_with_owner="${repo_name_with_owner#https://github.com/}"
  repo_name_with_owner="${repo_name_with_owner#git@github.com:}"
  repo_name_with_owner="${repo_name_with_owner%.git}"
  case "$repo_name_with_owner" in
    shader-slang/*)
      "$GH" pr comment "$pr_ref" --body '/ci all'
      ;;
  esac
}

PR_URL="$("$GH" pr create \
  --repo "$REPO" \
  --base "$BASE" \
  --head "$BRANCH" \
  --title "<title>" \
  --body-file "$BODY_FILE_ARG" \
  --assignee @me \
  "${DRAFT_ARGS[@]}" \
  "${LABEL_ARGS[@]}")" || exit 1
PR_URL="$(printf '%s\n' "$PR_URL" | clean_line)"
request_coderabbit_review_if_draft "$PR_URL"
trigger_shader_slang_ci_if_needed "$PR_URL"
printf '%s\n' "$PR_URL"
```

Keep `--assignee @me` in the command unless the user explicitly requests a
different assignee.

If the branch was pushed to a fork rather than the target repository, use
`--head "<user>:<branch>"`. Determine the fork owner from the push remote:

```bash
PUSH_URL="$("$GIT" remote get-url --push "$PUSH_REMOTE" | clean_line)"
HEAD_REPO="$("$GH" repo view "$PUSH_URL" --json nameWithOwner --jq .nameWithOwner | clean_line)"
HEAD_OWNER="${HEAD_REPO%%/*}"
PR_URL="$("$GH" pr create \
  --repo "$REPO" \
  --base "$BASE" \
  --head "$HEAD_OWNER:$BRANCH" \
  --title "<title>" \
  --body-file "$BODY_FILE_ARG" \
  --assignee @me \
  "${DRAFT_ARGS[@]}" \
  "${LABEL_ARGS[@]}")" || exit 1
PR_URL="$(printf '%s\n' "$PR_URL" | clean_line)"
request_coderabbit_review_if_draft "$PR_URL"
trigger_shader_slang_ci_if_needed "$PR_URL"
printf '%s\n' "$PR_URL"
```

For Windows PowerShell:

```powershell
$prUrl = gh.exe pr create `
  --repo $repo `
  --base $base `
  --head $branch `
  --title "PR title" `
  --body-file .\pr-body.md `
  --assignee "@me" `
  --draft `
  --label "pr: non-breaking"
gh.exe pr comment $prUrl --body "@coderabbitai review"
$repoNameWithOwner = $repo -replace '^https://github\.com/', '' -replace '^git@github\.com:', '' -replace '\.git$', ''
if ($repoNameWithOwner -like "shader-slang/*") {
  gh.exe pr comment $prUrl --body "/ci all"
}
$prUrl
```

Omit `--draft` only if the user passes `--no-draft` or explicitly requests a PR
that is ready for review.

## After Creation

Report the PR URL, the base branch, the head branch, whether a CodeRabbit review
request was posted, whether `/ci all` was posted, and whether any validation was
run. If PR creation fails
because the branch was not pushed to a usable remote or the target repo differs
from the local `origin`, explain the failure and ask before adding remotes or
changing push destinations.
