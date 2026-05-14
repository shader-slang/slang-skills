---
name: slang-pr-review
license: MIT
description: "Reproduces the shader-slang/slang production PR-review bot (anthropics/claude-code-action@v1 + .github/workflows/claude-pr-review.yml) locally — read-only. Same claude CLI, same user prompt, same system-prompt append, same model, same six .claude/agents/* subagents, same deepwiki MCP. Always dry-run: produces final-review.md and the calling workflow returns it via send_file. Never writes back to GitHub (no PR comments, no review posts). Used by the /slang-pr-review workflow."
provides: []
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
| `scripts/repro.sh` | (called by compose-and-run.sh) | The actual `claude` CLI invocation. Mirrors production byte-for-byte for read-only review. |
| `scripts/devin-fetch.sh` | Reviewer B | Drives `agent-browser` to load `app.devin.ai/review/...`, polls for "Analysis complete", expands flags, extracts the AI analysis + flag list to `devin-flags.md`. Exits 2 on auth-wall, 3 on timeout — workflow treats both as best-effort skip. |
| `scripts/summarize.py` | Summarize | Parses `stream.jsonl` and per-subagent `task_notification.output_file`s. Emits severity counts, per-subagent cost, drift signals. Counts GitHub-write tool attempts as a drift safety check (must be 0 — non-zero indicates the read-only allowlist leaked). |

## Modes

All three modes are read-only — the review is written to `final-review.md` and returned via `send_file`. Never posted to GitHub.

### `--mode pr` (most common)
`gh pr diff <PR> -R <REPO>` is the source of "what to review".

### `--mode branch`
`git diff <base>..<branch>` is the source.

### `--mode patch`
A unified diff (or markdown attachment containing one) is applied to a temp branch on the local `slang/` checkout. `git diff <temp_branch>` becomes the review target. After the run, the temp branch is deleted; `slang/master` is untouched.

## Byte-equivalence with production

The skill is pinned to a specific commit of `anthropics/claude-code-action`. The pin is in `reference/claude-code-action.lock`. The reference directory contains:

- `instructions.md` — what the action sends the SDK (verbatim system prompt preset reference, allowed-tools schema, MCP auto-injection rules)
- `instructions-overlay.md` — what `.github/workflows/claude-pr-review.yml` adds on top (user prompt, system-prompt append, tool allowlist, MCP config)
- `runs/run-25338177724.log` — a known-good production run log used as the byte-comparison fixture
- `validate.sh` — diffs five extracts from the run log against the same five extracts from this skill's prompt-templates and reports a 5/5 byte match

`validate.sh` runs in nanoclaw CI on every PR to this skill (and on a weekly schedule). When `claude-code-action` upstream ships a change that affects the prompt, the user-prompt template, the system-prompt append, the model ID, or the MCP server set, validate.sh fails. Procedure to update:

1. Fetch a fresh production run log (any successful run of `claude-pr-review.yml` on shader-slang/slang)
2. Update `reference/runs/<run_id>.log`, `reference/instructions.md`, `reference/instructions-overlay.md`, `prompt-templates/*` to match
3. Bump `reference/claude-code-action.lock` to the new commit SHA
4. Re-run `validate.sh`; PR lands when 5/5 byte-match restores

This is the same approach we used during initial harness development; promoted into a CI-enforced contract.

## Gotchas

- **mkdir / redirect retry dance.** The claude CLI sandbox blocks `mkdir tmp` and `> tmp/pr-diff.patch` under CWD. The model burns ~60 s retrying before giving up and using `gh pr diff` bare. Happens in production too — observed in the reference run. Pre-computing the diff out-of-band would skip this loop but break byte-equivalence; skill preserves the dance.
- **Subagent output files cleared by container restart.** `task_notification.output_file` paths in `stream.jsonl` point to `/tmp/...` — these vanish on restart. `compose-and-run.sh` includes a post-exit hook that copies them into `<run_dir>/subagents/<task_id>.output` before they're cleared.
- **gh auth is read-only.** `GH_TOKEN` only needs read access on the target repo for `gh pr diff`. The skill never posts back to GitHub — the read-only allowlist excludes `mcp__github__create_pull_request_review` / `add_issue_comment` / etc., and `summarize.py` flags any attempt as drift.
- **Stale `.local/bin` after restart.** Container restarts may wipe `~/.local/bin`. `install.sh` is idempotent — first call after a restart re-installs claude CLI.
- **Editing local REVIEW.md is for iteration only.** A/B-test changes to `/workspace/agent/slang/REVIEW.md` stay local; never push from the coworker. A real proposal goes via a separate PR to shader-slang/slang.
- **Devin scrape is brittle.** `devin-fetch.sh` keeps selectors minimal (heading text + `Flags` button). DOM changes upstream will break it; the script fails gracefully and the workflow treats Reviewer B as best-effort.
