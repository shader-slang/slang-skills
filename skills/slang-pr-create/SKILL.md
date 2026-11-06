---
allowed-tools: Bash Read Write Edit Grep Glob
argument-hint: '[--repo owner/repo-or-url-or-remote] [--no-draft] [--wsl]'
description: Create and publish a GitHub pull request for Slang work. By default the PR targets the upstream repository (the parent of the origin fork, or origin itself when origin is not a fork). The branch is pushed to origin, which is assumed to be the user's fork, and the PR is opened from the fork to the upstream repository. The PR is assigned to the authenticated GitHub account. It uses draft PRs only for shader-slang/* targets unless the user specifies another repository, remote, or draft option. The PR description is short, so that it stays readable in `git log`; a detailed description is posted as a PR comment. Use for Slang-related PR creation requests, including shader-slang/* targets even when the user does not explicitly name this skill. Handles WSL environments that require Windows-hosted tools unless --wsl is requested.
name: slang-pr-create
required-capabilities: shell git github-cli file-read
---
# Slang PR Create

Create a focused GitHub pull request from the current branch.

Assume that the working directory is a clone of the user's GitHub fork. The
process is:

1. Push the current branch to the fork (`origin`).
2. Open the PR from the fork to the upstream repository, which is the parent of
   the fork (for example, `shader-slang/slang`).

If `origin` is not a fork (for example, a clone of `shader-slang/slang` itself),
push to `origin` and open the PR in `origin`. If the user names a repo or
remote, open the PR in that repository instead. The branch is still pushed to
`origin`.

Use this skill for Slang-related requests to create, open, publish, or prepare
a PR. It can target any GitHub repository or git remote; requests targeting a
`shader-slang/*` repository should use this skill even when the user does not
explicitly invoke `/slang-pr-create`.

**Usage**: `/slang-pr-create [--repo owner/repo-or-url-or-remote] [--no-draft] [--wsl]`

PRs targeting `shader-slang/*` are created as drafts by default. PRs targeting
other repositories are created ready for review. Use `--no-draft` only when a
`shader-slang/*` PR should be ready for review immediately.

Every created PR is assigned to `@me`. In `gh`, `@me` is the GitHub account that
is logged in (the account that creates the PR). Do not assign anyone else unless
the user asks.

Only pass labels that are present in the target repository.

`--wsl` means "use native WSL tools" when running inside WSL. Without it,
require Windows-hosted `.exe` tools such as `gh.exe`. If they are missing, stop
and tell the user to install the Windows tools or rerun with `--wsl`.

### Two-part description

GitHub can use the PR description as the commit message when the PR is merged,
and a long description makes `git log` hard to read. So the description is split
in two parts:

1. **Short PR description** (the PR body). It can reach `git log`, so write it
   as plain text, not Markdown. Keep it to at most **1,000 characters**.

2. **Detailed description** (a PR comment). It has the full explanation. Post it
   directly after the PR is created. A comment is not part of the merge commit
   message, but readers can still find it on the PR page.

### Writing style

Write the PR title, the short description, and the detailed comment in Simplified
Technical English (STE). Load the `slang-ste-writing` skill before you write
them. Its main limits are:

- Use short sentences: 20 words for an instruction, 25 words for other
  sentences.
- Write one topic in each paragraph, with at most 6 sentences.
- Use the same word for the same thing every time.
- Use the active voice for instructions.
- Do not use the words in its "Words we do not use" table (for example,
  `utilize`, `ensure`, `robust`).

STE also helps with the 1,000-character limit, because short plain sentences
use fewer characters.

After you write the files and before you create the PR, run the checker of that
skill on both files. Fix each finding, then run the checker again:

```bash
python3 -I "<slang-ste-writing-dir>/scripts/ste_check.py" "$BODY_FILE"
python3 -I "<slang-ste-writing-dir>/scripts/ste_check.py" "$DETAIL_FILE"
```

The checker reports findings but does not block. Identifiers, code spans, and
technical names are exempt from the rules.

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

Write the short PR body and the detailed comment outside the tracked worktree,
then pass a Windows path from `wslpath -w` when `$GH` ends in `.exe`:

```bash
BODY_FILE="$("$GIT" rev-parse --git-path slang-pr-body.md | clean_line)"
DETAIL_FILE="$("$GIT" rev-parse --git-path slang-pr-detail.md | clean_line)"
if is_wsl && command -v wslpath >/dev/null 2>&1; then
  case "$BODY_FILE" in
    *\\*|[A-Za-z]:*) BODY_FILE="$(wslpath -u "$BODY_FILE")" ;;
  esac
  case "$DETAIL_FILE" in
    *\\*|[A-Za-z]:*) DETAIL_FILE="$(wslpath -u "$DETAIL_FILE")" ;;
  esac
fi
BODY_FILE_ARG="$BODY_FILE"
DETAIL_FILE_ARG="$DETAIL_FILE"
if is_wsl && [ "${GH%.exe}" != "$GH" ] && command -v wslpath >/dev/null 2>&1; then
  BODY_FILE_ARG="$(wslpath -w "$BODY_FILE")"
  DETAIL_FILE_ARG="$(wslpath -w "$DETAIL_FILE")"
fi
```

## Resolve Inputs

Use the repository from the user request when provided. Accept `--repo
owner/repo`, `--repo https://github.com/owner/repo`, `--repo <git-remote>`, a
bare positional `owner/repo`, a GitHub URL, or a bare positional git remote name
such as `origin` or `upstream`.

If a bare token with no slash matches `git remote`, treat that remote's URL as
the target repository. The branch is still pushed to `origin`.

If the bare token is `upstream` but no `upstream` git remote exists, infer
`shader-slang/<repo-name>` from the local `origin` repository name. Then forks
of repositories such as `shader-slang/slangpy` target the matching upstream
repository.

If no repository or remote is given, target the **upstream** repository, not
the fork. Look up `origin` on GitHub. When `origin` is a fork, the target is its
parent repository. When `origin` is not a fork, the target is `origin` itself.

An explicit `origin` argument is different: it targets the `origin` repository
itself, even if it is a fork.

The target is only the place where the PR is opened. The branch is always pushed
to `origin`, even when the target is another repository. When `origin` is a
fork, the PR head is `<fork-owner>:<branch>` (see "Create The PR").

Do not default to a specific `shader-slang/*` repository when any explicit
repository or remote argument was provided; fail instead if it cannot be
resolved.

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

TARGET_REMOTE=""
if [ -z "$TARGET_ARG" ]; then
  # Default: the upstream repository. Use the parent when origin is a fork,
  # otherwise origin itself (no fork).
  ORIGIN_URL="$("$GIT" remote get-url origin 2>/dev/null | clean_line || true)"
  if [ -z "$ORIGIN_URL" ]; then
    echo "No repository was given and the origin remote is missing"
    exit 1
  fi
  REPO="$("$GH" repo view "$ORIGIN_URL" --json isFork,parent,nameWithOwner \
    --jq 'if .isFork and .parent then "\(.parent.owner.login)/\(.parent.name)" else .nameWithOwner end' \
    | clean_line)"
  if [ -z "$REPO" ]; then
    echo "Could not resolve the upstream repository of origin: $ORIGIN_URL"
    exit 1
  fi
elif [[ "$TARGET_ARG" != */* && "$TARGET_ARG" != http://* && "$TARGET_ARG" != https://* && "$TARGET_ARG" != git@github.com:* ]]; then
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

Sort the known issue references into two groups. The short PR description lists
both groups (see "Short PR description"):

- **Fixed** issues: the PR fully fixes the issue. Write `Fixes #123`, or
  `Fixes owner/repo#123` for a cross-repository issue. GitHub closes these
  issues when the PR is merged.
- **Related** issues: the PR only touches, partly addresses, or depends on the
  issue, so it must stay open. Write `Related to #123`, or
  `Related to owner/repo#123`. Do not use a closing keyword for these.

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
and use it later for `gh pr create`.

Push to `origin`. Assume that `origin` is the user's fork. If `origin` is the
target repository itself, the user works without a fork and the push goes
directly to the target. If `origin` does not exist, use the remote that the
branch tracks, or the first remote that has a push URL.

If the push is denied, stop and tell the user. Do not create a fork or add a
remote without asking.

```bash
# Assume origin is the user's fork (or the target itself when the user has no fork).
if "$GIT" remote get-url --push origin >/dev/null 2>&1; then
  PUSH_REMOTE="origin"
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

### Short PR description

Prepare the short PR body in `$BODY_FILE`. It is **plain text, not Markdown**.
GitHub can use it as the merge commit message, and people read it in `git log`
in a terminal. The whole file must be at most **1,000 characters**.

Use this structure. Replace placeholder guidance with real content. Do not leave
empty labels or `[[...]]` placeholder text in the final text.

```text
[[One line per issue reference: "Fixes #123" for each fixed issue and
"Related to #456" for each related issue ("owner/repo#123" for another
repository). Omit these lines when no issue reference is known.]]

Summary: [[One to three sentences: what the PR changes.]]

Root cause: [[One to three sentences: why the problem happens. For a feature or
refactor with no defect, use the label "Motivation:" and state the reason for
the change.]]

Generated with [[the LLM that created the PR, with the tool name, for example
Claude Sonnet 5.5 (Claude Code)]]
```

Plain-text rules:

- Do not use Markdown. Do not write headings (`#`), bold or italic marks,
  backticks, code fences, tables, links in `[text](url)` form, or HTML.
- Start each part with a plain label and a colon: "Summary:" and "Root cause:".
- Put one blank line between the parts: the issue lines, the Summary, the Root
  cause, and the "Generated with" line.
- Wrap lines at 72 characters or fewer.
- Write names and identifiers as plain words, without backticks.
- If you need a list, write one item per line with a number and a period
  ("1. ..."). Do not use `-` or `*` bullets.
- A closing keyword line such as "Fixes #123" is plain text that GitHub reads.
  It is not Markdown.

Content rules:

- Do not put code traces, `file.cpp:line` references, a glossary, test logs, or
  a test plan in it. Those belong in the detailed comment.
- Name the LLM that you (the agent) actually used. If the agent environment
  gives an attribution line for PR descriptions, use that line, but write it as
  plain text (for example, write the tool name and not a Markdown link).
- Use at most one "Fixes" or "Related to" line per issue. Do not duplicate or
  invent issue references, and do not leave placeholder text. If no issue
  reference is known, omit these lines.
- Use the target repository's local issue number form (`#123`) for issues in
  the same repository, and `owner/repo#123` only for another repository.
- Keep the PR title short (about 72 characters or fewer, in the imperative
  mood). The title is the subject line of the merge commit.

If the PR is intentionally backward-compatibility breaking, add a short
"Breaking change:" part after the Root cause part (it is part of the
1,000-character limit):

```text
Breaking change:
1. Existing systems and shaders may ...
2. Work around or resolve this by ...
```

The "Breaking change:" part is required when the PR is intentionally
backward-compatibility breaking or has the `pr: breaking` label. It must explain
both the problems the PR may cause for existing systems and shaders, and how
users can work around or properly resolve those problems.

### Detailed description (PR comment)

Prepare the detailed description in `$DETAIL_FILE`. It is posted as a comment
after the PR is created, so it is not part of the merge commit message.

Use this structure. Omit any section that is not applicable. Replace placeholder
guidance with real content for sections that remain. Do not leave empty headings
or `[[...]]` placeholder text. Do not repeat the issue lines or the LLM line;
they are in the short description.

```markdown
_Detailed description. It is posted as a comment so that it stays out of the
merge commit message._

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
process report relies on (e.g., witness, facet, the fixpoint solver, a non-obvious
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
logs or a `## Test Plan` section. A GitHub comment can hold at most 65,536
characters; keep the detailed description well below that.

### Labels

Use at most one compatibility label: `pr: non-breaking` or `pr: breaking`. These
labels cannot coexist. Use `pr: breaking` only when the change is clearly
backward-compatibility breaking. Use `pr: non-breaking` only when the user says
the PR is non-breaking or the non-breaking classification is otherwise clear.
When the compatibility classification is unclear, do not guess and do not apply
either label. Compatibility labels are optional metadata; if the target
repository does not have the selected label, continue creating the PR without
that label instead of creating labels or blocking PR creation.
Only pass labels that exist in the target repository.

### Create the PR and post the detailed comment

Create the PR with the short description. Then post the detailed description
as a comment on the new PR.

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
  BREAKING_HEADING_REGEX='^Breaking change:'
  if ! grep -Eq "$BREAKING_HEADING_REGEX" "$BODY_FILE"; then
    echo "Breaking PRs must include a 'Breaking change:' part in the short PR description."
    exit 1
  fi
elif [ "$NON_BREAKING_CHANGE" = true ]; then
  COMPAT_LABEL="pr: non-breaking"
fi
if [ -n "$COMPAT_LABEL" ]; then
  add_label_if_available "$COMPAT_LABEL"
fi

# The short description must stay small enough to be readable in `git log`.
BODY_LIMIT=1000
BODY_CHARS="$(wc -m < "$BODY_FILE" | tr -d ' \r')"
if [ "$BODY_CHARS" -gt "$BODY_LIMIT" ]; then
  echo "The short PR description has $BODY_CHARS characters; the limit is $BODY_LIMIT."
  echo "Shorten it and move the details to $DETAIL_FILE."
  exit 1
fi

DRAFT_ARGS=()
if [ "$DRAFT" = true ]; then
  DRAFT_ARGS=(--draft)
fi

# The head is "<branch>" when the branch was pushed to the target repository,
# and "<owner>:<branch>" when it was pushed to a fork (the default case).
PUSH_URL="$("$GIT" remote get-url --push "$PUSH_REMOTE" | clean_line)"
HEAD_REPO="$("$GH" repo view "$PUSH_URL" --json nameWithOwner --jq .nameWithOwner | clean_line)"
if [ "$HEAD_REPO" = "$REPO" ]; then
  HEAD_REF="$PR_HEAD"
else
  HEAD_REF="${HEAD_REPO%%/*}:$PR_HEAD"
fi

PR_URL="$("$GH" pr create \
  --repo "$REPO" \
  --base "$BASE" \
  --head "$HEAD_REF" \
  --title "<title>" \
  --body-file "$BODY_FILE_ARG" \
  --assignee @me \
  "${DRAFT_ARGS[@]}" \
  "${LABEL_ARGS[@]}")" || exit 1
PR_URL="$(printf '%s\n' "$PR_URL" | clean_line)"
printf '%s\n' "$PR_URL"

# Post the detailed description as a comment. It is not part of the merge
# commit message.
if ! "$GH" pr comment "$PR_URL" --body-file "$DETAIL_FILE_ARG"; then
  printf 'The PR was created, but posting the detailed comment failed.\n' >&2
  printf 'Retry: %s pr comment %s --body-file %s\n' "$GH" "$PR_URL" "$DETAIL_FILE_ARG" >&2
fi
```

Keep `--assignee @me` in the command unless the user explicitly requests a
different assignee. `@me` resolves to the GitHub account that `$GH` is logged
in with, which is the account that creates the PR.

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
$detailFile = (git.exe rev-parse --git-path slang-pr-detail.md).Trim()

# The short description must stay small enough to be readable in `git log`.
$bodyLimit = 1000
$bodyChars = (Get-Content -Raw -LiteralPath $bodyFile).TrimEnd().Length
if ($bodyChars -gt $bodyLimit) {
  throw "The short PR description has $bodyChars characters; the limit is $bodyLimit."
}

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
$hasBreakingChangeSection = Select-String -LiteralPath $bodyFile -Pattern '^Breaking change:' -Quiet
if ($breakingChange -and -not $hasBreakingChangeSection) {
  throw "Breaking PRs must include a 'Breaking change:' part in the short PR description."
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

# The head is "<branch>" when the branch was pushed to the target repository,
# and "<owner>:<branch>" when it was pushed to a fork (the default case).
# $pushRemote is the remote that the branch was pushed to (origin by default).
$pushRemote = "origin"
$pushUrl = (git.exe remote get-url --push $pushRemote).Trim()
$headRepo = (& $GH repo view $pushUrl --json nameWithOwner --jq ".nameWithOwner").Trim()
if ($headRepo -ieq $repoNameWithOwner) {
  $headRef = $headBranch
} else {
  $headRef = "$($headRepo.Split('/')[0]):$headBranch"
}

$prCreateArgs = @(
  "pr", "create",
  "--repo", $repo,
  "--base", $base,
  "--head", $headRef,
  "--title", "PR title",
  "--body-file", $bodyFile,
  "--assignee", "@me"
)
if ($repoNameWithOwner -like "shader-slang/*" -and -not $noDraft) {
  $prCreateArgs += "--draft"
}
$prCreateArgs += $labelArgs
$prUrl = (& $GH @prCreateArgs).Trim()
$prUrl

# Post the detailed description as a comment. It is not part of the merge
# commit message.
& $GH pr comment $prUrl --body-file $detailFile
if ($LASTEXITCODE -ne 0) {
  Write-Warning "The PR was created, but posting the detailed comment failed."
  Write-Warning "Retry: $GH pr comment $prUrl --body-file $detailFile"
}
```

Omit `--draft` for non-`shader-slang/*` targets. Also omit it if the user passes
`--no-draft` or explicitly requests a `shader-slang/*` PR that is ready for
review (set `$noDraft = $true` in PowerShell).

## After Creation

Report the PR URL, the target repository (and whether it is the upstream of a
fork), the base branch, the published head branch (and whether it is on a fork), whether the push fell back to
a new remote branch name, the assignee, which labels were applied, the length of
the short description, whether the detailed comment was posted, and whether any
validation was run.

If PR creation fails because the branch was not pushed to a usable remote or the
target repo differs from the local `origin`, explain the failure and ask before
adding remotes or changing push destinations. If only the detailed comment
fails, say so and give the retry command.

## Terminology

Write the PR text in STE (see "Writing style"). Use the shared glossary in `skills/slang-glossary/` (start at `GLOSSARY-MAP.md`). Write the canonical term in prose and put a code identifier in backticks only when the identifier itself is meant. Never write a spelling the glossary lists under _Avoid_; the STE checker reports the unconditional ones. When a concept has no entry yet, use the word the surrounding code and docs use and say so in the PR text.
