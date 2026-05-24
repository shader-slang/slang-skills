---
name: slang-pr-create
description: Create and publish a GitHub pull request for Slang work, defaulting to shader-slang/slang and its default branch unless the user specifies another repository. Use when asked to open, create, publish, or prepare a PR for a Slang branch, including WSL environments that require Windows-hosted tools unless --wsl is requested.
argument-hint: "[--repo owner/repo-or-url] [--draft] [--wsl]"
allowed-tools: Bash Read Write Edit Grep Glob
required-capabilities: shell git github-cli file-read
---

# Slang PR Create

Create a focused GitHub pull request from the current branch. Default to
`shader-slang/slang`; if the user specifies a repo, use that repo instead.

**Usage**: `/slang-pr-create [--repo owner/repo-or-url] [--draft] [--wsl]`

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
if printf '%s\n' "$ARGS" | grep -Eq '(^|[[:space:]])--wsl([[:space:]]|$)'; then
  USE_WSL_TOOLS=true
  ARGS="$(printf '%s\n' "$ARGS" | sed -E 's/(^|[[:space:]])--wsl([[:space:]]|$)/ /; s/^[[:space:]]+//; s/[[:space:]]+$//')"
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
BASE="$("$GH" repo view "$REPO" --json defaultBranchRef --jq .defaultBranchRef.name | clean_line)"
BRANCH="$("$GIT" branch --show-current | clean_line)"
```

PowerShell / `gh.exe` equivalent:

```powershell
$repo = "shader-slang/slang"
$base = gh.exe repo view $repo --json defaultBranchRef --jq ".defaultBranchRef.name"
$branch = git branch --show-current
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
"$GIT" push -u origin HEAD
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

For `shader-slang/slang`, label the PR as `pr: non-breaking` by default unless
the change is intentionally breaking. For any other repo, only pass a label if
the repository has the label or the user explicitly requested one.

Create the PR:

```bash
LABEL_ARGS=()
if [ "$REPO" = "shader-slang/slang" ]; then
  LABEL_ARGS=(--label "pr: non-breaking")
fi

"$GH" pr create \
  --repo "$REPO" \
  --base "$BASE" \
  --head "$BRANCH" \
  --title "<title>" \
  --body-file "$BODY_FILE_ARG" \
  --assignee @me \
  "${LABEL_ARGS[@]}"
```

If the branch was pushed to a fork rather than the target repository, use
`--head "<user>:<branch>"`. Determine the fork owner from the push remote:

```bash
HEAD_REPO="$("$GH" repo view "$("$GIT" remote get-url --push origin)" --json nameWithOwner --jq .nameWithOwner | clean_line)"
HEAD_OWNER="${HEAD_REPO%%/*}"
"$GH" pr create \
  --repo "$REPO" \
  --base "$BASE" \
  --head "$HEAD_OWNER:$BRANCH" \
  --title "<title>" \
  --body-file "$BODY_FILE_ARG" \
  --assignee @me \
  "${LABEL_ARGS[@]}"
```

For Windows PowerShell:

```powershell
gh.exe pr create `
  --repo $repo `
  --base $base `
  --head $branch `
  --title "PR title" `
  --body-file .\pr-body.md `
  --assignee "@me" `
  --label "pr: non-breaking"
```

Use `--draft` only if the user requests a draft PR or the work is intentionally
not ready for review.

## After Creation

Report the PR URL printed by `$GH pr create`, the base branch, the head branch,
and whether any validation was run. If PR creation fails because the branch was
not pushed to a usable remote or the target repo differs from the local `origin`,
explain the failure and ask before adding remotes or changing push destinations.
