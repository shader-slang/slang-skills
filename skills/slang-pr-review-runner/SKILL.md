---
name: slang-pr-review-runner
license: MIT
description: "Reproduces the shader-slang/slang production PR-review bot (anthropics/claude-code-action@v1 + .github/workflows/claude-pr-review.yml) locally. Same claude CLI, same user prompt, same system-prompt append, same model, same six .claude/agents/* subagents, same deepwiki MCP. The inner CLI produces final-review.md; the wrapping workflow optionally posts it back to GitHub as a COMMENT-state review (event=COMMENT only, never APPROVE/REQUEST_CHANGES) when the orchestrator authorizes (via webhook trigger). Mirrors production's pre-cleanup (minimize prior bot reviews, resolve threads) and post-safety-net (dismiss any non-COMMENT bot reviews). Helper scripts: cleanup.sh (pre), post-review.sh (post). Used by the /slang-pr-review workflow."
provides: [code.review]
argument-hint: "[--mode pr|branch|patch] [--pr N|--branch ref|--patch path] [--repo owner/name] [--max-budget-usd $]"
allowed-tools: Bash Read Write Edit Grep Glob mcp__deepwiki__ask_question mcp__nanoclaw__send_message mcp__nanoclaw__send_file
---

# Slang PR Review

Bridges the `/slang-pr-review` workflow's *what* (review this PR) to the *how* (faithful reproduction of the production review pipeline). All scripts live alongside this file; the workflow is responsible for the protocol.

## Pick a script

| Script | Used in workflow Step | What it does |
|---|---|---|
| `scripts/install.sh` | Preflight | Idempotent install of `claude` CLI and `slang/` checkout. Safe to re-run. |
| `scripts/compose-and-run.sh` | Reviewer A | Top-level entry. Constructs prompt + flags + MCP config from the input mode and invokes `claude --print`. Writes a transcript directory under `transcripts/`. Returns `final-review.md`. With `--detach` it validates the flags, starts the run through `detach.sh`, prints the run directory and returns at once. |
| `scripts/detach.sh` | (called by compose-and-run.sh and run-clarity.sh with `--detach`) | `detach.sh <run-dir> -- <command...>`: starts the command in its own session (setsid + nohup, stdin `/dev/null`, stdout+stderr to `<run-dir>/run.log`), records `<run-dir>/pid` and, when the command ends, `<run-dir>/exit-status`. Prints the run directory. |
| `scripts/wait-run.sh` | Wait (after a detached dispatch) | `wait-run.sh <run-dir> [--timeout S] [--poll S] [--tail N]`: blocks until `<run-dir>/exit-status` appears and exits with that code, printing the last `--tail` lines (default 40) of `run.log` on a nonzero code. Exits 124 when `--timeout` (default 1200 s) passes with the run still going (call again), 125 when the recorded pid is gone with no status (the run died), 2 on usage error. |
| `scripts/repro.sh` | (called by compose-and-run.sh) | The actual `claude` CLI invocation. Mirrors production byte-for-byte, with `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1` exported so the six reviewer subagents run in the foreground. |
| `scripts/prestage.sh` | (called by compose-and-run.sh, pr mode) | Writes `tmp/pr-diff.patch`, `tmp/pr-files.txt` and `tmp/context.json` before the inner CLI starts, as production's pre-stage step does; fails on a phantom PR or an empty diff. |
| `scripts/claude-md-excludes.sh` | (called by repro.sh) | Prints the `--settings` JSON (`claudeMdExcludes`) that drops every `CLAUDE.md` above the checkout. Reviewer C's `run-clarity.sh` applies the same exclusion. |
| `scripts/devin-fetch.sh` | Reviewer B | Drives `agent-browser` to load `app.devin.ai/review/...`, polls for analysis completion (clicking the "View results" card when the analysis finishes while the page is open, then reloading once so the per-category counts render), captures commit-status freshness, expands the Vulnerabilities / Bugs / Flags / Informational panels, and extracts the AI analysis + vulnerability list + bug list + flag list + informational-finding list to `devin-flags.md`. Default timeout 30 minutes (`--max-minutes`). On timeout it writes `devin-page.txt` and the done-signal booleans into `devin-error.txt` so a renamed panel is diagnosable from the artifacts. Exits 2 on auth-wall, 3 on timeout, 4 on browser-launch-failure (transient — stale Chrome profile lock; the script clears it and retries once first) — workflow treats 2/3/4 as best-effort skip. |
| `scripts/cleanup.sh` | Pre-cleanup (before posting) | Minimizes prior bot review bodies as `OUTDATED`, resolves prior bot review threads, minimizes prior bot tracking comments. Targets `nv-slang-bot` only (configurable). Mirrors the "Clean up previous Claude reviews" step in production's claude-pr-review.yml. Best-effort — errors swallowed. |
| `scripts/post-review.sh` | Post (gated) | Posts the merged review as a `COMMENT`-state review (event=COMMENT only). On 403 (token lacks pull_requests:write), exits 3 so the wrapping workflow falls back to send_file. After posting, dismisses any APPROVED/CHANGES_REQUESTED reviews from the bot as a safety net (mirrors production's "Dismiss unauthorized bot approvals" step). |
| `scripts/post-back.sh` | Post-back (orchestration wrapper) | Convenience wrapper the workflow calls when it has decided to post: runs `cleanup.sh` then `post-review.sh` in sequence. One invocation, one exit code. Use this from the workflow rather than calling the two scripts manually. |
| `scripts/summarize.py` | Summarize | Parses `stream.jsonl` and per-subagent `task_notification.output_file`s. Emits severity counts, per-subagent cost, drift signals. The drift detector now flags submitted reviews with state ≠ COMMENT (formerly: any GitHub-write tool attempt). |

## Modes

All three modes produce `final-review.md`. Whether the merged review is then POSTED to GitHub is a separate decision made by the wrapping `/slang-pr-review` workflow — webhook-triggered runs (where a human tagged `@nv-slang-bot review` on the PR) post; chat-triggered runs return via `send_file` only.

### `--mode pr` (most common)
`gh pr diff <PR> -R <REPO>` is the source of "what to review".

### `--mode branch`
`git diff <base>..<branch>` is the source.

### `--mode patch`
A unified diff (or markdown attachment containing one) is applied to a temp branch on the local `slang/` checkout. `git diff <temp_branch>` becomes the review target. After the run, the temp branch is deleted; `slang/master` is untouched.

## Equivalence with production — and the deliberate gaps

The skill is pinned to a specific commit of `anthropics/claude-code-action` (`reference/claude-code-action.lock`). What the reviewer **sees** is byte-equivalent to production:

- ✅ Same model, same six `.claude/agents/*` subagents, same `REVIEW.md` protocol
- ✅ Same user prompt (the action passes the workflow's `prompt` input verbatim)
- ✅ Same `system-prompt-append.txt`
- ✅ Same `deepwiki` MCP server
- ✅ Same pre-staged `tmp/` artifacts (`prestage.sh`)
- ✅ Same instruction files (`claudeMdExcludes` drops every `CLAUDE.md` above the checkout)

What the reviewer **can do** deliberately diverges from production:

- ❌ **TRAILER differs** — production tells the model to post the review via GitHub MCP; this skill tells the model to output the markdown and stop. The wrapping workflow does the posting via `post-review.sh` (REST `POST /pulls/<n>/reviews` with event=COMMENT). Findings shouldn't change; the final assistant turn does.
- ❌ **MCP server set excludes `mcp-server-github`** — we use `gh api` and `gh api graphql` via Bash for both reads and writes. Equivalent capability, fewer dependencies.

- ❌ **`--setting-sources project`** — production also loads `user` and `local`; in the container those belong to the coworker.
- ❌ **CLI version** — production installs the release pinned by the action (see the lock); here the NanoClaw image's `claude` runs.

The inner CLI's tool allowlist now permits `gh api repos/*/pulls/*` and `gh api graphql*` so the wrapping workflow's helper scripts can run inside the same container session. Posting itself goes through `post-review.sh` rather than the inner CLI directly.

`reference/validate.sh` compares the newest `reference/runs/run-<id>.log` with this skill: user prompt, system-prompt append and model byte-exact; tool allowlist equal modulo the two divergences above; MCP server names equal. When it fails, follow `reference/README.md`.

If production changes drive different *findings* (e.g. a new subagent, a REVIEW.md protocol change), pull those into the local `slang/` checkout — the skill reads `REVIEW.md` and `.claude/agents/*` live, not from `prompt-templates/`.

## Gotchas

- **The diff is pre-staged.** `prestage.sh` writes `tmp/pr-diff.patch`, `tmp/pr-files.txt` and `tmp/context.json` before the inner CLI starts. If REVIEW.md Step 1 reports them missing or mismatched, re-run; do not let the model regenerate them.
- **Subagent output files cleared by container restart.** `task_notification.output_file` paths in `stream.jsonl` point to `/tmp/...` — these vanish on restart. `compose-and-run.sh` includes a post-exit hook that copies them into `<run_dir>/subagents/<task_id>.output` before they're cleared.
- **gh auth needs `pull_requests:write` on the target repo to post.** Read access is enough for the inner CLI's `gh pr diff`. Posting via `post-review.sh` requires the App installation token to grant `pull_requests:write`. On 403, `post-review.sh` exits 3 and the workflow falls back to `send_file` only — graceful degrade.
- **Reviews are always `event=COMMENT`.** Never `APPROVE` or `CHANGES_REQUESTED` — bots shouldn't gate human merges. `post-review.sh`'s safety net dismisses any non-COMMENT review the inner CLI accidentally submits, mirroring production's "Dismiss unauthorized bot approvals" step.
- **Cleanup targets the bot identity only.** Default `BOT_LOGIN=nv-slang-bot` — production's auto-reviews from `claude` / `github-actions` are deliberately left untouched, so this skill coexists with the upstream `claude-pr-review.yml` workflow without hiding its output.
- **Long runs are detached; the caller polls.** A review takes 60–95 minutes, longer than one Bash tool call may last, and a backgrounded job is killed with its process group when the call times out. `--detach` puts the run in its own session so no tool timeout reaches it, and `wait-run.sh` is the only way the caller should wait: call it in a loop with a `--timeout` well under the tool limit (20 minutes is the default) until it returns something other than 124. Read `final-review.md` only after `wait-run.sh` exited 0; the run's own stdout/stderr is in `<run-dir>/run.log`.
- **Reviewer subagents run in the foreground.** In print mode the CLI waits for a backgrounded subagent only up to an idle ceiling (`CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS`, ten minutes by default) and then ends the session with the text it has — one run shipped a 113-byte review that way. `repro.sh` exports `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1` so every `Agent` dispatch blocks until it returns; the minimum-output guard in `compose-and-run.sh` stays as the backstop.
- **The inner CLI is the image's `claude`.** `install.sh` installs one only when none is on PATH. Keep `~/.local/bin` last on PATH.
- **Ancestor `CLAUDE.md` files are excluded.** `repro.sh` passes `--settings` from `claude-md-excludes.sh` so the coworker document never reaches the reviewers; `INNER_CLAUDE_SETTINGS` overrides it. Keep the exclusion in the runner, not in the checkout.
- **Editing local REVIEW.md is for iteration only.** A/B-test changes to `/workspace/agent/slang/REVIEW.md` stay local; never push from the coworker. A real proposal goes via a separate PR to shader-slang/slang.
- **Devin scrape is brittle.** `devin-fetch.sh` keeps selectors minimal (heading text + Bugs/Flags buttons + commit-status popover via `aria-label`). The Vulnerabilities, Bugs, Flags and Informational panels are separate buttons, and Informational rows exist only as button DOM nodes (not in `innerText`); the script clicks all of them and harvests the rows directly. When expanding it never clicks a finding's `Post to GitHub` sibling (that would post to the PR). DOM changes upstream will break it; the script fails gracefully and the workflow treats Reviewer B as best-effort.
- **Chrome-launch failures are transient, not deterministic.** Chrome launches fine in the container without a dbus session bus. A `Failed to launch Chrome` / `without writing DevToolsActivePort` / `SingletonLock` error means a stale profile under `/tmp/agent-browser-*` from a prior crash. `devin-fetch.sh` closes the daemon, clears the profile dirs, and retries `open` once; a failure that survives the retry exits **4** (transient, retry later). Do not describe it as a "deterministic environment failure" — re-running the review usually succeeds.
- **DONE detection tolerates a lingering "in progress" banner.** Devin's "PR analysis in progress" text can flicker back on a fully-rendered page. The done-check only lets it veto when the positive signals (the analysis heading in either spelling, "Devin's AI analysis" or "Devin's analysis", or a "Read explanation" walkthrough button, plus a Vulnerabilities/Bugs/Flags/Checks summary) are absent, and requires the done state to hold across two consecutive polls, so a transient banner does not cause a false timeout while a genuine re-analysis (new head commit) keeps the poll waiting.
- **The first anonymous visit starts the analysis, and a finishing analysis shows a "View results" card.** Devin analyses a public PR on demand the first time its review page is opened. When the analysis finishes while the page is open, the sidebar replaces the per-category counts with "Analysis complete" + a "View results" button, and the counts never render on their own. The done-check clicks that button once and accepts "Analysis complete" as a summary signal; before expanding the panels the script reloads the page once if the counts are still missing, since a fresh load of a finished analysis renders them straight away.
