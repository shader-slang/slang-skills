---
allowed-tools: Bash Read Write Edit Grep Glob
argument-hint: '[--repo owner/repo-or-url-or-remote] [--no-draft] [--wsl]'
description: Create and publish a GitHub pull request for Slang work, defaulting to the local origin remote and using draft PRs only for shader-slang/* targets unless the user specifies another repository, remote, or draft option. Use for Slang-related PR creation requests, including shader-slang/* targets even when the user does not explicitly name this skill. Handles WSL environments that require Windows-hosted tools unless --wsl is requested.
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

PRs targeting `shader-slang/*` are created as drafts by default. PRs targeting
other repositories are created ready for review. Use `--no-draft` only when a
`shader-slang/*` PR should be ready for review immediately. Created PRs are
assigned to `@me` by default.
Only pass labels that are present in the target repository. If the target
repository has a `CoPilot` label, add it when creating the PR.
After creating a draft PR, request CodeRabbit review by commenting
`@coderabbitai review`.

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
if is_wsl && command -v wslpath >/dev/null 2>&1; then
  case "$BODY_FILE" in
    *\\*|[A-Za-z]:*) BODY_FILE="$(wslpath -u "$BODY_FILE")" ;;
  esac
fi
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
case "$REPO_NAME_WITH_OWNER" in
  shader-slang/*)
    ;;
  *)
    DRAFT=false
    ;;
esac
```

Try to determine the issue references that the PR is intended to fix before
creating the PR. Closing references should use `Fixes #123` for same-repository
issues and `Fixes owner/repo#123` for cross-repository issues.

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

### Branch Naming

Preserve the current branch whenever possible. Do **not** rename the current
branch or move the commits onto a new branch when the current branch is already
a topic branch (any branch whose name is not the target default branch). In that
case keep `BRANCH` as-is and create the PR from it.

Only create a new branch when the current branch is the default branch, i.e.
`BRANCH` is empty (detached HEAD) or `BRANCH` equals `BASE`. Never open a PR
whose head is the default branch. When this happens, choose a new branch name
that reflects what the committed changes do (for example, derived from the
primary commit subject), switch to it, and create the PR from that branch:

```bash
if [ -z "$BRANCH" ] || [ "$BRANCH" = "$BASE" ]; then
  # On the default branch (or detached HEAD): create a topic branch that
  # describes the change. Derive a slug from the latest commit subject and
  # sanitize it into a valid branch name.
  COMMIT_SUBJECT="$("$GIT" log -1 --pretty=%s | clean_line)"
  NEW_BRANCH="$(printf '%s' "$COMMIT_SUBJECT" \
    | tr '[:upper:]' '[:lower:]' \
    | sed -E 's/[^a-z0-9]+/-/g; s/^-+//; s/-+$//' \
    | cut -c1-50 \
    | sed -E 's/-+$//')"
  [ -z "$NEW_BRANCH" ] && NEW_BRANCH="slang-pr-$("$GIT" rev-parse --short HEAD | clean_line)"

  # Avoid clobbering an existing local branch of the same name.
  CANDIDATE="$NEW_BRANCH"
  suffix=1
  while "$GIT" show-ref --verify --quiet "refs/heads/$CANDIDATE"; do
    suffix=$((suffix + 1))
    CANDIDATE="${NEW_BRANCH}-${suffix}"
  done
  NEW_BRANCH="$CANDIDATE"

  "$GIT" switch -c "$NEW_BRANCH" || exit 1
  BRANCH="$NEW_BRANCH"
  printf 'Was on default branch %s; created topic branch %s for the PR.\n' "$BASE" "$BRANCH" >&2
fi
```

Prefer a descriptive slug, but you may instead ask the user for a branch name
when the change spans many commits or no single commit subject captures it.
After this step `BRANCH` always names a topic branch distinct from `BASE`.

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

Prepare a concise PR body in `$BODY_FILE`. Use this structure, omitting any
section that is not applicable to the PR. Replace placeholder guidance with real
content for sections that remain; do not leave empty headings or `[[...]]`
placeholder text in the final PR description.

```markdown
[[Add one line per confirmed issue, e.g., `Fixes #123` or `Fixes owner/repo#123`.
Omit this line when no issue reference is known.]]

## Motivation

[[The problem, grounded in a concrete example or motivating test case. Write for
a reviewer without the full context in their head.]]

## Proposed solution

[[The approach taken and why it is principled rather than a minimal-edit-distance
workaround.]]

## Change summary

[[The files/areas touched and what each one does. Wire claims to the source with
function names and `file.cpp:line` references.]]

## Concepts and vocabulary

[[A short glossary that restates only the codebase-specific or subtle terms the
process report relies on (e.g. witness, facet, the fixpoint solver, a non-obvious
distinction the fix hinges on). Do not explain basic, well-known concepts such as
interface or associated type — assume them. Omit this section if no such terms
are needed.]]

## Process report

[[Explain every change with a logical reason. For a change addressing a cascading
issue, describe the issue (with its motivating test case) and justify the fix with
a code trace — the exact functions/insts involved — explaining why it is necessary
and principled rather than a workaround. For any change that handles, guards, or
special-cases a particular input shape, answer the input-shape check: is that shape
itself correct and principled, or should its producer have been fixed instead? — so
a reviewer can confirm the fix sits at the right layer.]]
```

Ground each abstract claim in a concrete example, and wire explanations to the
source (function name and file, or `file.cpp:line`). Do not include validation
logs or a `## Test Plan` section in the PR description.

If the PR is intentionally backward-compatibility breaking, include this section
in the PR body:

```markdown
## Breaking change
1. Existing systems and shaders may ...
2. Work around or resolve this by ...
```

The `## Breaking change` section is required when the PR is intentionally
backward-compatibility breaking or has the `pr: breaking` label. It must explain
both the problems the PR may cause for existing systems and shaders, and how
users can work around or properly resolve those problems.

When one or more fixed issue references are known, put one `Fixes #123` line per
fixed issue at the top of the PR body. Use the target repository's local issue
number form for same-repository issues, and use `Fixes owner/repo#123` only for
cross-repository issues. Do not duplicate issue references, invent issue
references, or include placeholder closing text. If no issue reference is known,
omit `Fixes` lines.

Use at most one compatibility label: `pr: non-breaking` or `pr: breaking`. These
labels cannot coexist. Use `pr: breaking` only when the change is clearly
backward-compatibility breaking. Use `pr: non-breaking` only when the user says
the PR is non-breaking or the non-breaking classification is otherwise clear.
When the compatibility classification is unclear, do not guess and do not apply
either label. Compatibility labels are optional metadata; if the target
repository does not have the selected label, continue creating the PR without
that label instead of creating labels or blocking PR creation.
Only pass labels that exist in the target repository. This applies to
compatibility labels such as `pr: non-breaking` or `pr: breaking`, and to
integration labels such as `CoPilot`.

Create the PR:

```bash
LABEL_ARGS=()
LABEL_NAMES="$("$GH" label list \
  --repo "$REPO" \
  --limit 1000 \
  --json name \
  --jq '.[].name' 2>/dev/null | clean_line || true)"

repo_has_label() {
  label_name="$1"
  printf '%s\n' "$LABEL_NAMES" | grep -Fxq "$label_name"
}

add_label_if_available() {
  label_name="$1"
  if repo_has_label "$label_name"; then
    LABEL_ARGS+=(--label "$label_name")
  else
    printf 'Target repository is missing optional label: %s\n' "$label_name" >&2
    printf 'Creating the PR without that label.\n' >&2
  fi
}

BREAKING_CHANGE=false
NON_BREAKING_CHANGE=false
# Set BREAKING_CHANGE=true only when the user explicitly says the PR is breaking
# or the change is intentionally backward-compatibility breaking.
# Set NON_BREAKING_CHANGE=true only when the user says the PR is non-breaking or
# the non-breaking classification is otherwise clear. Leave both false when
# unclear.
COMPAT_LABEL=""
if [ "$BREAKING_CHANGE" = true ]; then
  COMPAT_LABEL="pr: breaking"
  BODY_FILE_READ="$BODY_FILE"
  if is_wsl && command -v wslpath >/dev/null 2>&1; then
    case "$BODY_FILE_READ" in
      *\\*|[A-Za-z]:*) BODY_FILE_READ="$(wslpath -u "$BODY_FILE_READ")" ;;
    esac
  fi
  BREAKING_HEADING_REGEX='^##[[:space:]]+Breaking change([[:space:]:]|$)'
  if ! grep -Eq "$BREAKING_HEADING_REGEX" "$BODY_FILE_READ"; then
    echo "Breaking PRs must include a '## Breaking change' section in the PR body."
    exit 1
  fi
elif [ "$NON_BREAKING_CHANGE" = true ]; then
  COMPAT_LABEL="pr: non-breaking"
fi
if [ -n "$COMPAT_LABEL" ]; then
  add_label_if_available "$COMPAT_LABEL"
fi

add_label_if_available "CoPilot"

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
printf '%s\n' "$PR_URL"
```

For Windows PowerShell:

```powershell
$GH = "gh.exe"
# Branch naming: preserve the current topic branch. Only when on the default
# branch (or detached HEAD) create a new topic branch named from the latest
# commit subject, then switch to it. Mirrors the Bash "Branch Naming" step.
if ([string]::IsNullOrEmpty($branch) -or $branch -eq $base) {
  $commitSubject = (git.exe log -1 --pretty=%s).Trim()
  $newBranch = $commitSubject.ToLower() -replace '[^a-z0-9]+', '-' -replace '^-+', '' -replace '-+$', ''
  if ($newBranch.Length -gt 50) {
    $newBranch = $newBranch.Substring(0, 50) -replace '-+$', ''
  }
  if ([string]::IsNullOrEmpty($newBranch)) {
    $shortHead = (git.exe rev-parse --short HEAD).Trim()
    $newBranch = "slang-pr-$shortHead"
  }

  $candidate = $newBranch
  $suffix = 1
  while (git.exe show-ref --verify --quiet "refs/heads/$candidate") {
    $suffix++
    $candidate = "${newBranch}-${suffix}"
  }
  $newBranch = $candidate

  git.exe switch -c $newBranch
  if ($LASTEXITCODE -ne 0) { exit 1 }
  $branch = $newBranch
  [Console]::Error.WriteLine("Was on default branch $base; created topic branch $branch for the PR.")
}

$headBranch = $branch
$repoNameWithOwner = $repo -replace '^https://github\.com/', '' -replace '^git@github\.com:', '' -replace '\.git$', ''
$bodyFile = (git.exe rev-parse --git-path slang-pr-body.md).Trim()
$breakingChange = $false
$nonBreakingChange = $false
# Set $breakingChange = $true only when the user explicitly says the PR is breaking
# or the change is intentionally backward-compatibility breaking.
# Set $nonBreakingChange = $true only when the user says the PR is non-breaking
# or the non-breaking classification is otherwise clear.
$compatLabel = $null
if ($breakingChange) {
  $compatLabel = "pr: breaking"
} elseif ($nonBreakingChange) {
  $compatLabel = "pr: non-breaking"
}
$hasBreakingChangeSection = Select-String -LiteralPath $bodyFile -SimpleMatch "## Breaking change" -Quiet
if ($breakingChange -and -not $hasBreakingChangeSection) {
  throw "Breaking PRs must include a '## Breaking change' section in the PR body."
}
$labelArgs = @()
$labelNames = @(& $GH label list `
  --repo $repoNameWithOwner `
  --limit 1000 `
  --json name `
  --jq ".[].name" 2>$null)
function Add-LabelIfAvailable {
  param([string]$LabelName)
  if ($labelNames | Where-Object { $_ -ceq $LabelName }) {
    $script:labelArgs += @("--label", $LabelName)
  } else {
    Write-Warning "Target repository is missing optional label: $LabelName"
    Write-Warning "Creating the PR without that label."
  }
}
if ($compatLabel) {
  Add-LabelIfAvailable $compatLabel
}
Add-LabelIfAvailable "CoPilot"
$prCreateArgs = @(
  "pr", "create",
  "--repo", $repo,
  "--base", $base,
  "--head", $headBranch,
  "--title", "PR title",
  "--body-file", $bodyFile,
  "--assignee", "@me"
)
if ($repoNameWithOwner -like "shader-slang/*") {
  $prCreateArgs += "--draft"
}
$prCreateArgs += $labelArgs
$prUrl = & $GH @prCreateArgs
if ($repoNameWithOwner -like "shader-slang/*") {
  & $GH pr comment $prUrl --body "@coderabbitai review"
}
$prUrl
```

Omit `--draft` for non-`shader-slang/*` targets. Also omit it if the user passes
`--no-draft` or explicitly requests a `shader-slang/*` PR that is ready for
review.

## After Creation

Report the PR URL, the base branch, the published head branch, whether the push
fell back to a new remote branch name, which labels were applied, whether a
CodeRabbit review request was posted, and whether any validation was run. If PR
creation fails because the branch was not pushed to a usable remote or the
target repo differs from the local `origin`, explain the failure and ask before
adding remotes or changing push destinations.
