# What shader-slang/slang adds on top of the action

The slang-specific overlay: `.github/workflows/claude-pr-review.yml` and the composite
action it calls, `.github/actions/claude-code-runner/action.yml`. Verified against the
fixture `runs/run-38546357585.log`.

## Workflow: `claude-pr-review.yml`

- **Trigger**: `pull_request_target` on `master` for opened / synchronize /
  ready_for_review / reopened, path-filtered to `source/**`, `tests/**`, `prelude/**`,
  `include/**`, `tools/**`, `CMakeLists.txt`, `cmake/**`; or `workflow_dispatch` with a
  PR number. Skips drafts, `[bot]` authors and `claude/` branches unless dispatched.
  Concurrency group per PR, cancel-in-progress. 60-minute job timeout.
- **Checkout**: the **base branch only**, depth 1. The PR head is never checked out.
- **Spec clone**: `shader-slang/spec` into `external/spec` (best effort).
- **Pre-stage** (trusted step, before any model runs):
  `tmp/pr-diff.patch` (`gh pr diff`), `tmp/pr-files.txt` (changed paths) and
  `tmp/context.json` (`repo, pr, base_sha, head_sha, diff_sha256`); fails the job if the
  diff is empty. REVIEW.md Step 1 verifies these and the prompt tells the model to use
  them as-is.
- **Cleanup** (`actions/github-script`): minimizes previous reviews and comments from
  the `claude` and `github-actions` logins as OUTDATED and resolves their threads.
- **PR Review**: the composite action, with the inputs below.
- **Safety net** (`if: always()`): dismisses any APPROVED / CHANGES_REQUESTED review
  from the bot logins. Bot reviews are COMMENT-only by construction.

### Inputs passed to the composite action

| Input | Value |
|---|---|
| `prompt` | the scaffold in `scripts/repro.sh` (validate.sh check 1): read REVIEW.md first; REPO / PR NUMBER; base checked out, diff pre-staged in `tmp/`; previous reviews minimized |
| `custom-instructions` | `prompt-templates/system-prompt-append.txt` (check 2) |
| `mcp-config` | `{"mcpServers": {"deepwiki": {"type": "http", "url": "https://mcp.deepwiki.com/mcp"}}}` (check 5) |
| `allowed-tools` | read-only Bash (`git diff/log/show/status`, `grep`, `cat/head/tail`, `ls/find/wc`, `sha256sum/shasum`, `gh pr diff/view/list/checks`, `gh api repos/*/pulls/*`, `gh api repos/*/issues/*`), `Read/View/Glob/GlobTool/Grep/GrepTool/Agent/BatchTool/Skill`, `Write(tmp/**)`, `Edit(tmp/**)`, the GitHub MCP read tools and the pending-review / inline-comment write tools, `mcp__deepwiki__ask_question` (check 4) |
| `max-turns` | 500 |
| `allowed-non-write-users` | `*` (fork PRs allowed; safe because of base-only checkout and COMMENT-only tools) |
| `allowed-bots` | `nv-slang-bot` |
| `nv-inference-*-model` | repository variables `CLAUDE_NV_OPUS_MODEL` / `_SONNET_MODEL` / `_HAIKU_MODEL` |
| `use-sticky-comment`, `track-progress` | false |

## Composite action: `claude-code-runner`

- **Auth**: `CLAUDE_AUTH_PROVIDER` (default `llmgw`); production uses `nv-inference`,
  which sets `ANTHROPIC_BASE_URL` to the NV inference portal and the model ids in the
  `aws/anthropic/...` format. Raw credentials are cleared from the environment before
  the action runs and again in a final cleanup step.
- **Model**: for `nv-inference`, the Opus id from `nv-inference-opus-model`
  (production: `aws/anthropic/bedrock-claude-opus-5-5[1m]`, validate.sh check 3). The
  same three ids go into the step `env` *and* `settings.env` so sub-agents inherit them.
- **Quoting guard**: fails if `custom-instructions` contains an unbalanced double
  quote, because the string is interpolated into `claude_args` and a stray quote would
  swallow the flags after it.
- **`claude_args`** handed to `anthropics/claude-code-action@v1`:
  `--append-system-prompt "<custom-instructions>" --model <model> --max-turns <n>
  --allowedTools "<allowed-tools>" --mcp-config '<mcp-config>'`.
- **`settings`**: the model env block plus `GITHUB_REPOSITORY`, `GITHUB_EVENT_NAME`,
  `GITHUB_ACTOR`, `DISABLE_TELEMETRY=1`, `CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS=1`.

## What this skill mirrors and where it deliberately differs

Mirrored byte for byte (validate.sh): the prompt scaffold, the system-prompt append,
the model, the Bash/Read tool allowlist, the MCP config. Also mirrored: base-branch
checkout, pre-staged `tmp/` artifacts, the six project sub-agents, REVIEW.md read live
from the checkout.

Deliberate differences, all on the posting side or forced by the container:

| Production | This skill | Why |
|---|---|---|
| Model posts the review through the GitHub MCP pending-review tools | Trailer tells the model to print the review; `post-review.sh` posts it (COMMENT only) when the workflow authorizes | chat-triggered runs must not touch GitHub |
| `mcp-server-github` + inline-comment server injected | deepwiki only; `gh api` and `gh api graphql` allowed for the wrapping helpers | fewer dependencies, same capability |
| `settingSources: user, project, local` | `--setting-sources project` | the container's user and local scopes belong to the coworker, not the reviewer |
| Checkout has no parent directories with instructions | `claudeMdExcludes` for every ancestor of the checkout | the checkout lives under the coworker's group directory |
| CLI pinned by the action release (2.1.299 at v1.0.249) | the NanoClaw image's `claude` | the platform pins and tests one CLI for every coworker |
| Sub-agents may run in the background; print mode stops waiting for a quiet one after `CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS` | `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1`, every sub-agent in the foreground | a run that ends before its reviewers return produces a truncated review; the findings themselves do not depend on the scheduling |
