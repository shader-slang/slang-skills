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
| `scripts/compose-and-run.sh` | Reviewer A | Top-level entry. Constructs prompt + flags + MCP config from the input mode and invokes `claude --print`. Writes a transcript directory under `transcripts/`. Returns `final-review.md`. |
| `scripts/repro.sh` | (called by compose-and-run.sh) | The actual `claude` CLI invocation. Mirrors production byte-for-byte. |
| `scripts/devin-fetch.sh` | Reviewer B | Drives `agent-browser` to load `app.devin.ai/review/...`, polls for analysis completion, captures commit-status freshness, expands the Bugs and Flags panels, and extracts the AI analysis + bug list + flag list to `devin-flags.md`. Default timeout 30 minutes. Exits 2 on auth-wall, 3 on timeout — workflow treats both as best-effort skip. |
| `scripts/cleanup.sh` | Pre-cleanup (before posting) | Minimizes prior bot review bodies as `OUTDATED`, resolves prior bot review threads, minimizes prior bot tracking comments. Targets `nv-slang-bot` only (configurable). Mirrors the "Clean up previous Claude reviews" step in production's claude-pr-review.yml. Best-effort — errors swallowed. |
| `scripts/post-review.sh` | Post (gated) | Posts the merged review as a `COMMENT`-state review (event=COMMENT only). On 403 (token lacks pull_requests:write), exits 3 so the wrapping workflow falls back to send_file. After posting, dismisses any APPROVED/CHANGES_REQUESTED reviews from the bot as a safety net (mirrors production's "Dismiss unauthorized bot approvals" step). |
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
- ✅ Same user-prompt scaffold (REPO / PR NUMBER / "read REVIEW.md FIRST" preamble)
- ✅ Same `system-prompt-append.txt`
- ✅ Same `deepwiki` MCP server

What the reviewer **can do** deliberately diverges from production:

- ❌ **TRAILER differs** — production tells the model to post the review via GitHub MCP; this skill tells the model to output the markdown and stop. The wrapping workflow does the posting via `post-review.sh` (REST `POST /pulls/<n>/reviews` with event=COMMENT). Findings shouldn't change; the final assistant turn does.
- ❌ **MCP server set excludes `mcp-server-github`** — we use `gh api` and `gh api graphql` via Bash for both reads and writes. Equivalent capability, fewer dependencies.

The inner CLI's tool allowlist now permits `gh api repos/*/pulls/*` and `gh api graphql*` so the wrapping workflow's helper scripts can run inside the same container session. Posting itself goes through `post-review.sh` rather than the inner CLI directly.

`validate.sh` checks the byte-equivalent extracts (model ID, user-prompt scaffold, system-prompt append, subagent set, deepwiki MCP). It does NOT diff the trailer, tool allowlist, or MCP set — those are intentionally divergent. When `claude-code-action` upstream ships a change that affects the prompt scaffold, system-prompt append, model ID, or non-GitHub MCP server set, validate.sh fails. Procedure to update:

1. Fetch a fresh production run log (any successful run of `claude-pr-review.yml` on shader-slang/slang)
2. Update `reference/runs/<run_id>.log`, `reference/instructions.md`, `reference/instructions-overlay.md`, `prompt-templates/*` to match (skipping live-mode-only fields)
3. Bump `reference/claude-code-action.lock` to the new commit SHA
4. Re-run `validate.sh`; PR lands when the read-only-relevant extracts byte-match again

If production changes drive different *findings* (e.g. a new subagent, a REVIEW.md protocol change), pull those into the local `slang/` checkout — the skill reads `REVIEW.md` and `.claude/agents/*` live, not from `prompt-templates/`.

## Gotchas

- **mkdir / redirect retry dance.** The claude CLI sandbox blocks `mkdir tmp` and `> tmp/pr-diff.patch` under CWD. The model burns ~60 s retrying before giving up and using `gh pr diff` bare. Happens in production too — observed in the reference run. Pre-computing the diff out-of-band would skip this loop but break byte-equivalence; skill preserves the dance.
- **Subagent output files cleared by container restart.** `task_notification.output_file` paths in `stream.jsonl` point to `/tmp/...` — these vanish on restart. `compose-and-run.sh` includes a post-exit hook that copies them into `<run_dir>/subagents/<task_id>.output` before they're cleared.
- **gh auth needs `pull_requests:write` on the target repo to post.** Read access is enough for the inner CLI's `gh pr diff`. Posting via `post-review.sh` requires the App installation token to grant `pull_requests:write`. On 403, `post-review.sh` exits 3 and the workflow falls back to `send_file` only — graceful degrade.
- **Reviews are always `event=COMMENT`.** Never `APPROVE` or `CHANGES_REQUESTED` — bots shouldn't gate human merges. `post-review.sh`'s safety net dismisses any non-COMMENT review the inner CLI accidentally submits, mirroring production's "Dismiss unauthorized bot approvals" step.
- **Cleanup targets the bot identity only.** Default `BOT_LOGIN=nv-slang-bot` — production's auto-reviews from `claude` / `github-actions` are deliberately left untouched, so this skill coexists with the upstream `claude-pr-review.yml` workflow without hiding its output.
- **Stale `.local/bin` after restart.** Container restarts may wipe `~/.local/bin`. `install.sh` is idempotent — first call after a restart re-installs claude CLI.
- **Editing local REVIEW.md is for iteration only.** A/B-test changes to `/workspace/agent/slang/REVIEW.md` stay local; never push from the coworker. A real proposal goes via a separate PR to shader-slang/slang.
- **Devin scrape is brittle.** `devin-fetch.sh` keeps selectors minimal (heading text + Bugs/Flags buttons + commit-status popover via `aria-label`). The 2026 UI split the single "N Flags" toggle into separate Bugs and Flags buttons; the script clicks both. DOM changes upstream will break it; the script fails gracefully and the workflow treats Reviewer B as best-effort.
