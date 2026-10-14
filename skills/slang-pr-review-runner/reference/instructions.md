# What `anthropics/claude-code-action` does at the pinned version

Generic runtime facts, no slang specifics (those are in `instructions-overlay.md`).
Source: the action's `base-action/action.yml` and `base-action/src/run-claude.ts` at
the tag in `claude-code-action.lock`, cross-checked against the fixture in `runs/`.

## Setup the action performs before Claude runs

1. Installs Bun 1.3.14 and a **pinned Claude Code CLI** with
   `curl -fsSL https://claude.ai/install.sh | bash -s -- $CLAUDE_CODE_VERSION`
   (three attempts, 120 s each). The pin lives in `base-action/action.yml` and moves
   with every action release (current value: `claude_code_version` in the lock). The binary
   lands at `/home/runner/.local/bin/claude` and is passed to the SDK as
   `pathToClaudeCodeExecutable`. `path_to_claude_code_executable` input skips this.
2. Writes `~/.claude/settings.json` from the `settings` input (JSON) and merges
   `enableAllProjectMcpServers: true` into it. The caller's `settings.env` block is the
   only way to set environment variables that reach sub-agents.
3. Writes the prompt to `/home/runner/work/_temp/claude-prompts/claude-prompt.txt`.
4. Starts its own MCP servers and merges them with the caller's `--mcp-config`: a GitHub
   MCP server (`mcp__github__*`) and an
   inline-comment server (`mcp__github_inline_comment__create_inline_comment`). They are
   present in the inner CLI's tool list; `allowedTools` decides which the model may call.

## How it runs Claude

The action uses the Agent SDK's `query()` with the CLI above. The options it logs as
`SDK options:`:

| Option | Value |
|---|---|
| `model` | from `--model` in `claude_args` |
| `maxTurns` | from `--max-turns` in `claude_args` (500 in production) |
| `allowedTools` | from `--allowedTools` in `claude_args`, split on commas |
| `systemPrompt` | `{ type: "preset", preset: "claude_code" }` plus the `--append-system-prompt` string from `claude_args` |
| `settingSources` | `["user", "project", "local"]` |
| `pathToClaudeCodeExecutable` | `/home/runner/.local/bin/claude` |

Consequences for a mirror:

- The CLI is in print mode and streams `stream-json`; the action captures the final
  assistant text and writes it to the execution file the workflow may post.
- **Instruction files**: `settingSources` includes `project`, so every `CLAUDE.md` from
  the cwd (`/home/runner/work/slang/slang`) up to `/` loads. On a GitHub runner nothing
  sits above the checkout, so the inner CLI sees exactly the repository's own
  `CLAUDE.md`, its `@` imports and `.claude/agents/*`. A mirror whose checkout has
  parents carrying instructions must exclude them (this skill does, with
  `claudeMdExcludes`).
- **Sub-agents** come from the checkout's `.claude/agents/*` (project scope). The action
  sets no `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS`; print mode waits for backgrounded
  sub-agents with the CLI's default idle ceiling.
- The action passes no `--settings`, `--permission-mode` or `--dangerously-skip-permissions`;
  permissions come from `allowedTools` alone.

## Environment the action exposes to the CLI

From the composite caller's step `env` and `settings.env`: `ANTHROPIC_BASE_URL`,
`ANTHROPIC_DEFAULT_OPUS_MODEL` / `_SONNET_MODEL` / `_HAIKU_MODEL`, `GITHUB_REPOSITORY`,
`GITHUB_EVENT_NAME`, `GITHUB_ACTOR`, `DISABLE_TELEMETRY=1`,
`CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS=1`, plus the GitHub token the action obtained
(`github_token` input) for `gh` and the GitHub MCP server.
