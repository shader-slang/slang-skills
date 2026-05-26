---
allowed-tools: Bash Read Write Edit Grep Glob
argument-hint: '[--repo owner/repo-or-url-or-remote] [--no-draft] [--wsl]'
description: Create and publish a GitHub pull request for Slang work, defaulting to a draft PR against the local origin remote and its default branch unless the user specifies another repository or remote. Use for Slang-related PR creation requests, including shader-slang/* targets even when the user does not explicitly name this skill. Handles WSL environments that require Windows-hosted tools unless --wsl is requested.
name: slang-pr-create
required-capabilities: shell git github-cli file-read
---
# Slang PR Create

Create a focused GitHub pull request from the current branch. Default to the
repository configured by the local `origin` remote; if the user specifies a repo
or remote, use that target instead.
Use this skill for Slang-related requests to create, open, publish, or prepare
a PR. It can target any GitHub repository or git remote, defaulting to local
`origin`; requests targeting a `shader-slang/*` repository should use this skill
even when the user does not explicitly invoke `/slang-pr-create`.

**Usage**: `/slang-pr-create [--repo owner/repo-or-url-or-remote] [--no-draft] [--wsl]`

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
owner/repo`, `--repo https://github.com/owner/repo`, `--repo <git-remote>`, a
bare positional `owner/repo`, a GitHub URL, or a bare positional git remote name
such as `origin` or `upstream`.

If a bare token with no slash matches `git remote`, treat that remote's URL as
the target repository and prefer that same remote as the push remote. If the bare
token is `upstream` but no `upstream` git remote exists, infer
`shader-slang/<repo-name>` from the local `origin` repository name, so forks of
repositories such as `shader-slang/slangpy` target the matching upstream
repository. If omitted, behave as if `origin` was provided. Do not default to a
specific `shader-slang/*` repository when any explicit repository or remote
argument was provided; fail instead if it cannot be resolved.

```bash
# Parse the remaining skill arguments after `--wsl` and `--no-draft` are removed.
# shellcheck disable=SC2086
set -- $ARGS
TARGET_ARG=""
while [ $# -gt 0 ]; do
  case "$1" in
    --repo)
      shift
      if [ $# -eq 0 ] || [ -z "${1:-}" ] || [[ "${1:-}" == --* ]]; then
        echo "Missing value for --repo"
        exit 1
      fi
      TARGET_ARG="${1:-}"
      ;;
    --repo=*)
      if [ -z "${1#--repo=}" ]; then
        echo "Missing value for --repo"
        exit 1
      fi
      TARGET_ARG="${1#--repo=}"
      ;;
    *)
      if [ -z "$TARGET_ARG" ]; then
        TARGET_ARG="$1"
      fi
      ;;
  esac
  shift
done
if [ -z "$TARGET_ARG" ]; then
  TARGET_ARG="origin"
fi

TARGET_REMOTE=""
if [[ "$TARGET_ARG" != */* && "$TARGET_ARG" != http://* && "$TARGET_ARG" != https://* && "$TARGET_ARG" != git@github.com:* ]]; then
  if "$GIT" remote get-url "$TARGET_ARG" >/dev/null 2>&1; then
    TARGET_REMOTE="$TARGET_ARG"
    TARGET_URL="$("$GIT" remote get-url "$TARGET_REMOTE" | clean_line)"
    REPO="$TARGET_URL"
  elif [ "$TARGET_ARG" = "upstream" ]; then
    ORIGIN_URL="$("$GIT" remote get-url origin 2>/dev/null | clean_line || true)"
    if [ -z "$ORIGIN_URL" ]; then
      echo "Could not infer shader-slang upstream target because the origin remote is missing"
      exit 1
    fi
    ORIGIN_REPO_NAME="${ORIGIN_URL%/}"
    ORIGIN_REPO_NAME="${ORIGIN_REPO_NAME##*/}"
    ORIGIN_REPO_NAME="${ORIGIN_REPO_NAME%.git}"
    if [ -z "$ORIGIN_REPO_NAME" ]; then
      echo "Could not infer shader-slang upstream target from origin URL: $ORIGIN_URL"
      exit 1
    fi
    REPO="shader-slang/$ORIGIN_REPO_NAME"
  else
    echo "Could not resolve requested or default PR target as a GitHub repo or git remote: $TARGET_ARG"
    exit 1
  fi
else
  REPO="$TARGET_ARG"
fi
REPO="$("$GH" repo view "$REPO" --json nameWithOwner --jq .nameWithOwner | clean_line)"
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

This snippet assumes `$repo` has already been resolved and normalized using the
same input-resolution rules described above. Do not use the placeholder value
literally.

```powershell
$repo = "<resolved-target-repo>"
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

Push the branch if needed. Track the remote branch that was actually published
and use it later for `gh pr create`:

If the same-name push is rejected because the remote branch already exists or
has diverged, push `HEAD` to a new remote branch name and create the PR from that
new branch. For authentication, permission, or missing-remote failures, stop
instead of trying a new branch name.

```bash
if [ -n "${TARGET_REMOTE:-}" ]; then
  PUSH_REMOTE="$TARGET_REMOTE"
else
  PUSH_REMOTE="$("$GIT" config --get "branch.$BRANCH.remote" | clean_line || true)"
fi
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

PUBLISHED_BRANCH="$BRANCH"
PR_HEAD="$PUBLISHED_BRANCH"
PUSH_LOG="$(mktemp "${TMPDIR:-/tmp}/slang-pr-push.XXXXXX")"
trap 'rm -f "$PUSH_LOG"' EXIT
if ! "$GIT" push -u "$PUSH_REMOTE" "HEAD:refs/heads/$PUBLISHED_BRANCH" 2>"$PUSH_LOG"; then
  PUSH_OUTPUT="$(clean_line < "$PUSH_LOG")"
  if printf '%s\n' "$PUSH_OUTPUT" | grep -Eiq 'non-fast-forward|fetch first|stale info|already exists|remote contains work that you do not have'; then
    SHORT_HEAD="$("$GIT" rev-parse --short HEAD | clean_line)"
    PUBLISHED_BRANCH="${BRANCH}-${SHORT_HEAD}"
    suffix=1
    while "$GIT" ls-remote --exit-code --heads "$PUSH_REMOTE" "$PUBLISHED_BRANCH" >/dev/null 2>&1; do
      suffix=$((suffix + 1))
      PUBLISHED_BRANCH="${BRANCH}-${SHORT_HEAD}-${suffix}"
    done
    printf '%s\n' "$PUSH_OUTPUT" >&2
    printf 'Push to %s/%s was rejected; retrying as %s/%s.\n' "$PUSH_REMOTE" "$BRANCH" "$PUSH_REMOTE" "$PUBLISHED_BRANCH" >&2
    "$GIT" push -u "$PUSH_REMOTE" "HEAD:refs/heads/$PUBLISHED_BRANCH" || exit 1
    PR_HEAD="$PUBLISHED_BRANCH"
  else
    printf '%s\n' "$PUSH_OUTPUT" >&2
    exit 1
  fi
fi
```

Prepare a concise PR body in `$BODY_FILE`. Use this structure:

```markdown
[[Add one line per confirmed issue, e.g., `Fixes #123` or `Fixes owner/repo#123`.
Omit this line when no issue reference is known.]]

## Summary of the problem from the end user perspective

[[Very concise and succinct. Limit to one or two sentences.]]

### Minimal repro shader; if applicable

[[A few lines of Shader code snippet from the issue description or the new tests]]

## Root cause

[[Very concise and succinct. Limit to one or two sentences.]]

## Solution in this PR

[[Very concise and succinct. Limit to one or two sentences.]]

### Notes to the reviewers; where to focus on

[[Very concise and succinct. Easy to read and understand walkthrough]]

## Related PRs in the past

[[List of PRs in the past that were related to the issue and code lines]]
```

Do not include validation logs or a `## Test Plan` section in the PR
description.

If the PR is intentionally backward-compatibility breaking, include this section
in the PR body:

```markdown
## Breaking change
1. Existing systems and shaders may ...
2. Work around or resolve this by ...
```

The `## Breaking change` section is required when the PR has the `pr: breaking`
label. It must explain both the problems the PR may cause for existing systems
and shaders, and how users can work around or properly resolve those problems.

When one or more fixed issue references are known, put one `Fixes #123` line per
fixed issue at the top of the PR body. Use the target repository's local issue
number form for same-repository issues, and use `Fixes owner/repo#123` only for
cross-repository issues. Do not duplicate issue references, invent issue
references, or include placeholder closing text. If no issue reference is known,
omit `Fixes` lines.

Every PR must have exactly one compatibility label: `pr: non-breaking` or
`pr: breaking`. These labels cannot coexist. Use `pr: non-breaking` by default
unless the user explicitly says the change is breaking or the change is
intentionally backward-compatibility breaking. Use `pr: breaking` only for
breaking changes, and only when the PR body includes the required
`## Breaking change` section described above. Do not silently omit the
compatibility label; if the target repository does not have the selected label,
stop and ask before creating labels or changing the target repository.

Create the PR:

```bash
LABEL_ARGS=()
BREAKING_CHANGE=false
# Set BREAKING_CHANGE=true only when the user explicitly says the PR is breaking
# or the change is intentionally backward-compatibility breaking.
COMPAT_LABEL="pr: non-breaking"
if [ "$BREAKING_CHANGE" = true ]; then
  COMPAT_LABEL="pr: breaking"
  BODY_FILE_READ="$BODY_FILE"
  if is_wsl && command -v wslpath >/dev/null 2>&1; then
    case "$BODY_FILE_READ" in
      [A-Za-z]:*) BODY_FILE_READ="$(wslpath -u "$BODY_FILE_READ")" ;;
    esac
  fi
  if ! grep -Fxq '## Breaking change' "$BODY_FILE_READ"; then
    echo "PRs labeled 'pr: breaking' must include a '## Breaking change' section in the PR body."
    exit 1
  fi
fi
if ! "$GH" label list --repo "$REPO" --limit 200 --json name --jq '.[].name' | clean_line | grep -Fxq "$COMPAT_LABEL"; then
  echo "Target repository is missing required compatibility label: $COMPAT_LABEL"
  echo "Create the label or choose a target repository that has it before creating the PR."
  exit 1
fi
LABEL_ARGS=(--label "$COMPAT_LABEL")
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
  --head "$PR_HEAD" \
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
`--head "<user>:<branch>"` with the published branch name from `PR_HEAD`.
Determine the fork owner from the push remote:

```bash
PUSH_URL="$("$GIT" remote get-url --push "$PUSH_REMOTE" | clean_line)"
HEAD_REPO="$("$GH" repo view "$PUSH_URL" --json nameWithOwner --jq .nameWithOwner | clean_line)"
HEAD_OWNER="${HEAD_REPO%%/*}"
PR_URL="$("$GH" pr create \
  --repo "$REPO" \
  --base "$BASE" \
  --head "$HEAD_OWNER:$PR_HEAD" \
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
$headBranch = $branch
$repoNameWithOwner = $repo -replace '^https://github\.com/', '' -replace '^git@github\.com:', '' -replace '\.git$', ''
$breakingChange = $false
# Set $breakingChange = $true only when the user explicitly says the PR is breaking
# or the change is intentionally backward-compatibility breaking.
$compatLabel = if ($breakingChange) { "pr: breaking" } else { "pr: non-breaking" }
if ($breakingChange -and -not (Select-String -LiteralPath ".\pr-body.md" -SimpleMatch "## Breaking change" -Quiet)) {
  throw "PRs labeled 'pr: breaking' must include a '## Breaking change' section in the PR body."
}
$labels = @(gh.exe label list --repo $repo --limit 200 --json name --jq ".[].name")
if ($labels -notcontains $compatLabel) {
  throw "Target repository is missing required compatibility label: $compatLabel"
}
$labelArgs = @("--label", $compatLabel)
$prUrl = gh.exe pr create `
  --repo $repo `
  --base $base `
  --head $headBranch `
  --title "PR title" `
  --body-file .\pr-body.md `
  --assignee "@me" `
  --draft `
  @labelArgs
gh.exe pr comment $prUrl --body "@coderabbitai review"
if ($repoNameWithOwner -like "shader-slang/*") {
  gh.exe pr comment $prUrl --body "/ci all"
}
$prUrl
```

Omit `--draft` only if the user passes `--no-draft` or explicitly requests a PR
that is ready for review.

## After Creation

Report the PR URL, the base branch, the published head branch, whether the push
fell back to a new remote branch name, whether a CodeRabbit review request was
posted, whether `/ci all` was posted, and whether any validation was run. If PR
creation fails because the branch was not pushed to a usable remote or the target
repo differs from the local `origin`, explain the failure and ask before adding
remotes or changing push destinations.
