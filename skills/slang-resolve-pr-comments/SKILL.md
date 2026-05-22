---
name: slang-resolve-pr-comments
description: Resolve GitHub PR review feedback and CI failures. Use when asked to monitor a PR, handle LLM review threads, notify the user about draft/WIP/DNI review-blocking LLM messages, leave human review threads for human resolution, fix failing checks, rebase merge conflicts, and push updates until the PR is clean.
argument-hint: "<PR URL or number> [--single-pass]"
allowed-tools: Bash Read Write Edit Grep Glob ScheduleWakeup
required-capabilities: shell git github-cli file-read file-edit search
---

# Resolve GitHub Review Feedback

Use this skill to keep a GitHub PR moving until all CI checks pass and LLM review threads have been addressed and resolved by the agent. Human-owned threads are left unresolved — they are outside the agent's control and must be resolved by the human reviewers themselves.

## Agent Compatibility

This skill is written for any agent that can run shell commands, inspect and edit files, use `git`/`gh`, and optionally schedule a non-blocking follow-up. Treat named tools as capability examples, not hard requirements:

- Shell commands: `Bash`, terminal, `exec_command`, or any equivalent command runner.
- File work: `Read`/`Write`/`Edit`, `apply_patch`, or any equivalent file inspection and editing tools.
- Search: `Grep`/`Glob`, `rg`, or any equivalent repository search tools.
- Follow-up scheduling: `ScheduleWakeup`, a native reminder/resume tool, a background task scheduler, or no scheduler.

The `argument-hint`, `allowed-tools`, and `required-capabilities` metadata are Claude Code compatibility hints. Other agents may ignore them. When `$ARGUMENTS` appears below, use the PR URL or PR number from the user's prompt or from the current agent host's invocation argument.

## Prerequisites

- GitHub CLI (`gh`) is installed and authenticated for the PR repository.
- The `gh` token can read PR reviews/checks and push to the PR branch.
- A PR URL or PR number is provided by the user or agent invocation. In Claude Code slash commands, this arrives in `$ARGUMENTS`. If it is missing, ask the user for the PR.
- Optional: `--single-pass` disables automatic follow-up scheduling. In single-pass mode, report what remains pending, when to check again, and the exact rerun prompt/command instead of scheduling the next pass.

Initialize the PR selector once before any use, adapting the input variable to the current agent host:

```bash
# For Claude Code slash commands, ARGUMENTS contains the prompt argument.
# For other agents, replace ARGUMENTS with the host's invocation variable or set PR directly.
ARGS="${ARGUMENTS:-}"
SINGLE_PASS=false
if printf '%s\n' "$ARGS" | grep -Eq '(^|[[:space:]])--single-pass([[:space:]]|$)'; then
  SINGLE_PASS=true
  ARGS="$(printf '%s\n' "$ARGS" | sed -E 's/(^|[[:space:]])--single-pass([[:space:]]|$)/ /; s/^[[:space:]]+//; s/[[:space:]]+$//')"
fi
PR="$ARGS"
if [ -z "$PR" ]; then
  echo "Missing PR argument (URL or number)."
  exit 1
fi
```

Check before making changes:

```bash
gh auth status
git status --short
gh pr view "$PR" --json number,title,url,baseRefName,headRefName,headRepository,headRepositoryOwner,mergeStateStatus,isDraft
```

If `git status --short` shows any output, **stop and ask the user** how to proceed before continuing. Do not commit, stash, or discard anything automatically. Present the list of changed/untracked files and offer these options:

1. **Commit all changes** — ask for a commit message, then `git add -A && git commit -m "<message>"`.
2. **Commit only staged changes** — if `git diff --cached --name-only` is non-empty, ask for a commit message, then `git commit -m "<message>"` (leaves unstaged changes untouched).
3. **Stash changes** — run `git stash push -m "slang-resolve-pr-comments stash"` to set them aside, then proceed with the current HEAD.
4. **Abort** — stop the skill so the user can handle the changes manually.

Wait for the user's choice before continuing.

## Main Loop

Repeat this workflow periodically until the PR has no unresolved, non-outdated LLM-owned review feedback and all required checks pass. Between iterations, **do not use `sleep`** or block the live session. Use the current agent host's non-blocking follow-up facility when one exists; otherwise report the pending state and the exact prompt/command the user or orchestrator should rerun later, then return.

1. Check out the PR branch:

   ```bash
   gh pr checkout "$PR"
   git fetch --all --prune
   git submodule update --init --recursive
   ```

   This repo uses git submodules. Run `git submodule update --init --recursive` after any update to the local branch — e.g. `gh pr checkout`, `git pull`, or `git rebase` (and again after resolving merge conflicts — see below) — so submodule references stay in sync with the checked-out commit. A bare `git fetch` only updates remote-tracking refs and does not require a submodule sync on its own.

2. Inspect PR state, checks, mergeability, review-blocking notices, and review threads.
3. Fix actionable review feedback and CI failures.
4. Commit PR modifications as new commits and push them to the PR branch.
5. After pushing new commits, update the PR description if the new commits made it stale or inaccurate (see **PR Description Updates** below).
6. Reply to LLM review feedback and resolve only the LLM-owned threads that have been addressed.
7. Leave human-owned threads unresolved for the human reviewer to resolve manually.
8. At the end of each pass, check the Completion Criteria below:
   - If **all criteria are met**: report the PR is clean and **do not reschedule** — the loop is done.
   - Otherwise: schedule or request the next pass as described below, then return. The next pass should re-enter this skill with the same PR argument.

Stop (do not reschedule) only if blocked by missing credentials, missing push permission, an ambiguous human decision, or local changes that cannot be safely preserved.

**Continuing the next iteration** — at the end of every pass where work remains, prefer a non-blocking follow-up.

**Choosing `<interval>`:** Pick a value that keeps the conversation context cache warm —
staying under the cache TTL avoids paying a full cold re-read on every wakeup. Use
`cache_ttl_seconds - 60` as the interval, giving a 60 s safety margin. At the current
5-minute (300 s) TTL the default is **240 s**. If you know the cache TTL has changed,
recalculate accordingly. Never use a value at or above the TTL itself.

In Claude Code, call `ScheduleWakeup`:

```text
ScheduleWakeup(
  delaySeconds = <interval>,
  prompt       = "/slang-resolve-pr-comments <PR>",
  reason       = "polling PR <PR> for new review feedback"
)
```

For other agents, use the host's native equivalent if available. If no scheduling/resume tool exists, stop after reporting:

- What is still pending.
- When to check again — use 240 s by default (see **Choosing `<interval>`** above if the cache TTL differs).
- The exact rerun prompt, for example `/slang-resolve-pr-comments <PR>` (substituting `<PR>` with the actual PR URL or number) or the equivalent invocation in the current agent. If the original run used `--single-pass`, include `--single-pass` in the rerun prompt.

## Review-Blocking PR State

Before processing normal review feedback, check whether the PR is in a state where LLM reviewers may intentionally skip review:

```bash
gh pr view "$PR" --json title,isDraft,url
```

Treat the PR as review-blocked when it is a draft or when the title contains markers such as `WIP`, `DNI`, `DNM`, `do not review`, `do not merge`, or similar wording. Also inspect LLM comments for messages saying that review was skipped, paused, or unavailable because the PR is draft, WIP, DNI, or otherwise not ready for review.

If an LLM left a review-blocking message:

1. Notify the user with the PR URL, the LLM comment URL, and the exact blocking reason.
2. Do not change the draft state or title unless the user explicitly asks.
3. Do not treat the message as code feedback, and do not mark the thread resolved on behalf of the user.
4. Let the user resolve the situation by marking the PR ready for review, changing the title, or otherwise addressing the blocker.
5. If the PR is review-blocked, report the blocker and proceed to the **Completion Criteria** section (which handles single-pass vs. continuous monitoring) to schedule or request the next pass and return.

## Commit Policy

When the PR is modified for any reason, preserve the change history by creating a new commit for the modification. Do not use `git commit --amend` for review fixes, CI fixes, conflict-resolution follow-up edits, formatting changes, or any other PR update.

Use concise commit messages that describe the reason for the follow-up change, for example:

```bash
git add <changed-files>
git commit -m "Address review feedback"
git push
```

## PR Description Updates

After pushing any new commit to the PR branch, check whether the PR description still accurately reflects what the PR does. Update it when the new commits change the scope, behavior, or rationale in a way that makes the existing description stale, misleading, or incomplete. Examples of changes that warrant a description update:

- A review fix changes user-visible behavior, the public API, or configuration that the description documents.
- New commits add, remove, or rename functionality beyond what the description mentions.
- The description references a test plan, follow-up TODOs, or known limitations that are no longer accurate after the new commits.
- Conflict resolution or rebase work materially changes what is included in the PR.

Skip the update when the new commits are purely cosmetic (formatting, typo fixes, comment tweaks) or when they only address narrow review feedback that does not change the summary-level meaning of the PR.

Fetch the current description, edit it, and push the update with `gh`:

```bash
gh pr view "$PR" --json body --jq .body > /tmp/pr-body.md
# Edit /tmp/pr-body.md to reflect the current state of the PR.
gh pr edit "$PR" --body-file /tmp/pr-body.md
```

Preserve any existing sections (summary, test plan, generated-by footers, issue links) unless they are now inaccurate. Do not rewrite the description from scratch when a targeted edit will do.

## Review Threads

Use GitHub GraphQL to list review threads, because `gh pr view` does not expose all thread resolution state:

```bash
PR_NUMBER="$(gh pr view "$PR" --json number --jq .number)"
OWNER="$(gh pr view "$PR" --json baseRepository --jq .baseRepository.owner.login)"
REPO="$(gh pr view "$PR" --json baseRepository --jq .baseRepository.name)"

gh api graphql -F owner="$OWNER" -F repo="$REPO" -F pr="$PR_NUMBER" -f query='
query($owner:String!, $repo:String!, $pr:Int!, $after:String) {
  repository(owner:$owner, name:$repo) {
    pullRequest(number:$pr) {
      reviewThreads(first:100, after:$after) {
        pageInfo { hasNextPage endCursor }
        nodes {
          id
          isResolved
          isOutdated
          path
          line
          startLine
          comments(last:100) {
            nodes {
              id
              url
              body
              author { login __typename }
              createdAt
            }
          }
        }
      }
    }
  }
}'
```

Classify threads conservatively:

Check these in order — the first matching rule wins:

- **`bmillsNV`**: this account exists only to absorb review-request email spam and is not an actual reviewer. Ignore any review requests, assignments, or threads attributed to `bmillsNV` — do not treat them as human or LLM feedback, do not reply, and do not block completion on them. Checked first so this holds even if the account is ever a service/bot account.
- **LLM review feedback**: the author's `__typename` is `Bot` (from the GraphQL response), or the author is clearly an automated LLM reviewer by login — such as Copilot, CodeRabbit, Claude, Codex, OpenAI, Gemini, Greptile or another bot whose comment identifies itself as AI review feedback.
- **Human feedback**: the author is a person, the `author` field is `null` (deleted account — treat as human to be safe), or the source is ambiguous.
- **CI/static-analysis bot output**: handle it as CI feedback unless it is clearly an LLM review thread.

For each unresolved, non-outdated (`isResolved = false` and `isOutdated = false`) LLM thread:

1. Read the full thread and relevant code.
2. Apply the fix, or determine that the suggestion is invalid with evidence.
3. Run focused validation.
4. Push the fix if code changed.
5. Reply on the thread with what changed, what validation ran, or why no code change was needed. **Always start the reply body with `[Agent] `** so readers can distinguish agent-posted comments from comments left by the human account owner.
6. Resolve the thread only after the reply is posted and the issue is actually addressed.

Reply to an LLM thread:

```bash
gh api graphql -F thread="$THREAD_ID" -F body="$REPLY_BODY" -f query='
mutation($thread:ID!, $body:String!) {
  addPullRequestReviewThreadReply(input:{pullRequestReviewThreadId:$thread, body:$body}) {
    comment { url }
  }
}'
```

Resolve an addressed LLM thread:

```bash
gh api graphql -F thread="$THREAD_ID" -f query='
mutation($thread:ID!) {
  resolveReviewThread(input:{threadId:$thread}) {
    thread { id isResolved }
  }
}'
```

For human threads, do not mark them resolved. If you fixed the issue, reply with a concise summary and ask the reviewer to resolve the thread if satisfied. **Always start the reply body with `[Agent] `** so readers can distinguish agent-posted comments from comments left by the human account owner.

If `pageInfo.hasNextPage` is true, paginate and inspect every review thread before deciding that the PR has no remaining feedback.
For pagination, repeat the query adding `-F after="$END_CURSOR"` (using the value from `pageInfo.endCursor`) to the `gh api graphql` command, with `reviewThreads(first:100, after:$after)` in the query.

## CI Failures

Inspect checks with:

```bash
gh pr checks "$PR"
gh run list --branch "$(git branch --show-current)" --limit 10
RUN_ID="$(gh run list --branch "$(git branch --show-current)" --status failure --limit 1 --json databaseId --jq '.[0].databaseId')"
if [ -n "$RUN_ID" ] && [ "$RUN_ID" != "null" ]; then
  gh run view "$RUN_ID" --log-failed
else
  echo "No failed workflow runs found for current branch."
fi
```

For each failure:

1. Identify the failing job and command from the logs.
2. **Determine if the failure looks intermittent or infra-related** (see below). If so, retry instead of attempting a code fix.
3. Otherwise, reproduce locally when feasible.
4. Fix the code or test.
5. Run the narrowest reliable validation first, then broader validation when the change warrants it.
6. Push to the PR branch.
7. Continue monitoring until the new checks finish.

### Intermittent / Infra Failures

Treat a failure as intermittent or infrastructure-related when the logs show any of:

- Network errors: timeouts, connection resets, DNS failures, `curl`/`wget` failures fetching dependencies or artifacts
- Resource exhaustion: out-of-memory kills, disk-full errors, CPU throttling, runner eviction
- Runner/infra issues: runner setup failures, Docker pull failures, missing environment variables injected by CI, agent disconnects
- Flaky test output: assertions about timing, port conflicts, race conditions with no code change that could explain it
- Lock or concurrency errors in the CI infrastructure itself (e.g., package-manager lock conflicts unrelated to code changes)
- Errors in unrelated jobs (e.g., a deploy job fails while the compile job that touches your code succeeds)

When a failure matches any of these, **do not attempt a code fix**. Instead, retry the failed run:

```bash
gh run rerun "$RUN_ID" --failed
```

The `--failed` flag re-runs only the failed jobs, not the entire workflow.

**Waiting for the retry option to become available:** GitHub only allows rerunning once the run `status` is `completed` (the only terminal status value; `queued` and `in_progress` are non-terminal). The run outcome — `success`, `failure`, `cancelled`, etc. — is stored in the separate `conclusion` field, which is only populated after `status` becomes `completed`. The script below correctly gates on `.status == "completed"` before attempting the rerun. If the run is still in progress when you first inspect it, schedule a wakeup and try again:

```bash
RUN_STATUS="$(gh run view "$RUN_ID" --json status --jq .status)"
if [ "$RUN_STATUS" != "completed" ]; then
  echo "Run $RUN_ID is still $RUN_STATUS — will retry rerun after next wakeup."
else
  gh run rerun "$RUN_ID" --failed
fi
```

After issuing a rerun, proceed to the **Completion Criteria** section to schedule or request the next pass, then verify in the following pass whether the retried run passed. If the same job fails again with the same infra-looking error, retry once more (up to **3 total attempts** for the same run). After 3 consecutive infra-looking failures, stop retrying and report the pattern to the user — the infra issue may be persistent and require human intervention.

If checks are still running and there is no review work to do, do not block — use a non-blocking check, then proceed to the **Completion Criteria** section to schedule or request the next pass and return:

```bash
gh pr checks "$PR"
```

## Merge Conflicts And Auto-Rebase Failures

**Do not rebase proactively.** Only rebase onto the base branch when GitHub explicitly reports merge conflicts (i.e. `mergeStateStatus` is `DIRTY` or the PR shows a conflict that blocks merge). If a push is rejected because the remote PR branch has newer commits, synchronize with the remote first (e.g. `git pull --rebase`). If the branch is merely behind the base branch but has no conflicts and you have no local changes to push, leave it alone — GitHub's auto-merge will rebase or merge it when the time comes.

If GitHub reports that auto-merge or auto-rebase cannot continue because conflicts must be resolved, update the PR branch manually.

Inspect merge state:

```bash
gh pr view "$PR" --json baseRefName,headRefName,mergeStateStatus,headRepository,headRepositoryOwner
```

Resolve by rebasing onto the latest base branch:

```bash
BASE="$(gh pr view "$PR" --json baseRefName --jq .baseRefName)"
HEAD_BRANCH="$(gh pr view "$PR" --json headRefName --jq .headRefName)"
BASE_REPO="$(gh pr view "$PR" --json baseRepository --jq .baseRepository.nameWithOwner)"
BASE_REPO_ESC="$(printf '%s' "$BASE_REPO" | sed -e 's/[][(){}.^$*+?|\\]/\\&/g')"
BASE_REMOTE="$(git remote -v | grep -Em1 "github\.com[:/]${BASE_REPO_ESC}(\.git)?([[:space:]]|$)" | awk '{print $1}')"
if [ -z "$BASE_REMOTE" ]; then
  BASE_REMOTE="upstream"
  if ! git remote get-url "$BASE_REMOTE" 2>/dev/null; then
    echo "Could not determine base remote for $BASE_REPO and 'upstream' does not exist"
    exit 1
  fi
fi
git fetch "$BASE_REMOTE" "$BASE"
git rebase "$BASE_REMOTE/$BASE"
```

Resolve conflicts in the files, then continue:

```bash
git add <resolved-files>
git rebase --continue
git submodule update --init --recursive
```

Always re-run `git submodule update --init --recursive` after a rebase or conflict resolution so submodule pointers match the new HEAD.

Run relevant validation, then push with a lease:

```bash
HEAD_REPO="$(gh pr view "$PR" --json headRepository --jq .headRepository.nameWithOwner)"
HEAD_REPO_ESC="$(printf '%s' "$HEAD_REPO" | sed -e 's/[][(){}.^$*+?|\\]/\\&/g')"
PUSH_REMOTE="$(git remote -v | grep -Em1 "github\.com[:/]${HEAD_REPO_ESC}(\.git)?([[:space:]]|$)" | awk '{print $1}')"
if [ -z "$PUSH_REMOTE" ]; then
  gh pr checkout "$PR"
  PUSH_REMOTE="$(git remote -v | grep -Em1 "github\.com[:/]${HEAD_REPO_ESC}(\.git)?([[:space:]]|$)" | awk '{print $1}')"
fi
if [ -z "$PUSH_REMOTE" ]; then
  echo "Could not determine push remote for $HEAD_REPO"
  exit 1
fi
git push --force-with-lease "$PUSH_REMOTE" "HEAD:$HEAD_BRANCH"
```

## Completion Criteria

After every pass, evaluate whether to stop or reschedule:

**Stop and report success** when all of these are true — do not schedule another pass:

- `gh pr checks "$PR"` shows all required checks passing.
- The PR is not in a draft/WIP/DNI-style state that LLM reviewers reported as blocking review.
- There are no unresolved, non-outdated LLM review threads.
- `gh pr view "$PR" --json mergeStateStatus --jq .mergeStateStatus` does not report `DIRTY` (actual merge conflicts) or `UNKNOWN` (still calculating). A status of `BEHIND` (branch is behind base but no conflicts) is acceptable — GitHub auto-merge handles it.
- All local commits needed for the fixes have been pushed to the PR branch.

**Continue later** when any of the above is not yet true. If a single-pass run was requested (`--single-pass` or `SINGLE_PASS=true`) or scheduling is unavailable, report what is still pending, when to check again, and the exact rerun prompt/command, then return. Otherwise, schedule a non-blocking follow-up when the current agent host supports one, using `delaySeconds = <interval>` (see **Choosing `<interval>`** above), then return.

**The following conditions are not grounds for rescheduling:**

1. **Unresolved human review threads**: human-owned threads are outside the agent's control. Stop rescheduling and report "PR is ready — waiting for human reviewers to resolve N thread(s)."
