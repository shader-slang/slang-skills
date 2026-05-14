---
name: slang-pr-review
license: MIT
description: "Reproduces the shader-slang/slang production PR-review bot (anthropics/claude-code-action@v1 + .github/workflows/claude-pr-review.yml) locally. Same claude CLI, same user prompt, same system-prompt append, same model, same six .claude/agents/* subagents, same deepwiki MCP. Dry-run by default; --live-on-fork posts as nv-slang-bot[bot] but only against szihs/* repos. Used by the /slang-pr-review workflow."
provides: []
argument-hint: "[--mode pr|branch|patch] [--pr N|--branch ref|--patch path] [--repo owner/name] [--live-on-fork] [--max-budget-usd $]"
allowed-tools: Bash Read Write Edit Grep Glob mcp__deepwiki__ask_question mcp__nanoclaw__send_message mcp__nanoclaw__send_file
---

# Slang PR Review

Bridges the `/slang-pr-review` workflow's *what* (review this PR) to the *how* (faithful reproduction of the production review pipeline). All scripts live alongside this file; the workflow is responsible for the protocol.

## Pick a script

| Script | Used in workflow Step | What it does |
|---|---|---|
| `scripts/install.sh` | Step 1 (Preflight) | Idempotent install of `claude` CLI, `mcp-server-github`, and `slang/` checkout. Safe to re-run. |
| `scripts/compose-and-run.sh` | Step 2 (Compose & run) | Top-level entry. Constructs prompt + flags + MCP config from the input mode and invokes `claude --print`. Writes a transcript directory under `transcripts/`. |
| `scripts/repro.sh` | (called by compose-and-run.sh) | The actual `claude` CLI invocation. Mirrors production byte-for-byte. |
| `scripts/cleanup.sh` | (called by compose-and-run.sh in `--live-on-fork`) | Pre-step: minimize prior `nv-slang-bot[bot]` reviews / threads / comments on the target PR via GraphQL. Faithful port of `claude-pr-review.yml` lines 131–184. Refuses any non-szihs repo. |
| `scripts/summarize.py` | Step 3 (Summarize) | Parses `stream.jsonl`, `posted-review.json`, and per-subagent `task_notification.output_file`s. Emits severity counts, per-subagent cost, drift signals. |

## Modes

### `--mode pr` (most common)
`gh pr diff <PR> -R <REPO>` is the source of "what to review". Live-on-fork mode posts the review back to that PR via the github MCP `create_pull_request_review` tool with `event="COMMENT"`.

### `--mode branch`
`git diff <base>..<branch>` is the source. No canonical PR → never posts; final review is sent via `mcp__nanoclaw__send_file`.

### `--mode patch`
A unified diff (or markdown attachment containing one) is applied to a temp branch on the local `slang/` checkout. `git diff <temp_branch>` becomes the review target. After the run, the temp branch is deleted; `slang/master` is untouched. Never posts.

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

## Tool-name divergence (live-on-fork)

The npm `@modelcontextprotocol/server-github` package this skill installs exposes `mcp__github__create_pull_request_review` (single-shot with inline `comments: [...]`). Production uses the Docker `ghcr.io/github/github-mcp-server` image which exposes a 3-call pending-review trio (`create_pending_pull_request_review` + `add_comment_to_pending_review` + `submit_pending_pull_request_review`).

The LIVE-ON-FORK trailer in `prompt-templates/user-prompt.template` tells the model to collapse the 3-call pattern into one `create_pull_request_review` call with `event="COMMENT"`. Final posted review on GitHub is semantically equivalent; internal mechanism is not.

If maintenance burden of the divergence becomes painful, the alternative is shipping a thin gh-cli-backed wrapper MCP that exposes the production tool names. Out of scope for this skill's v1.

## Gotchas

- **mkdir / redirect retry dance.** The claude CLI sandbox blocks `mkdir tmp` and `> tmp/pr-diff.patch` under CWD. The model burns ~60 s retrying before giving up and using `gh pr diff` bare. Happens in production too — observed in the reference run. Pre-computing the diff out-of-band would skip this loop but break byte-equivalence; skill preserves the dance.
- **Subagent output files cleared by container restart.** `task_notification.output_file` paths in `stream.jsonl` point to `/tmp/...` — these vanish on restart. `compose-and-run.sh` includes a post-exit hook that copies them into `<run_dir>/subagents/<task_id>.output` before they're cleared.
- **Live-on-fork token swap.** `GH_TOKEN` must resolve to a token with `pull_requests: write` and `issues: write` on the target szihs repo. nv-slang-bot installation 122269597 (szihs) qualifies. The slang-coworkers installation does NOT; pushing or PR-creation will 403.
- **Stale `.local/bin` after restart.** Container restarts may wipe `~/.local/bin`. `install.sh` is idempotent — first call after a restart re-installs claude CLI + mcp-server-github.
- **Editing local REVIEW.md is for iteration only.** A/B-test changes to `/workspace/agent/slang/REVIEW.md` stay local; never push from the coworker. A real proposal goes via a separate PR to shader-slang/slang.
