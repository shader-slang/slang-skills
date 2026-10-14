# reference/

What the skill must stay byte-equivalent to.

## Layout

| File | Purpose |
|---|---|
| `claude-code-action.lock` | Pinned commit of `anthropics/claude-code-action` that the skill mirrors, the production run it was observed in, the Claude Code CLI that action release installs, and the production model id (`model=`, read by `validate.sh` when `ANTHROPIC_DEFAULT_OPUS_MODEL` is unset). |
| `instructions.md` | What the action does at the pinned version — CLI install, settings, injected MCP servers, the SDK options it runs Claude with. Generic, no slang specifics. |
| `instructions-overlay.md` | What `shader-slang/slang/.github/workflows/claude-pr-review.yml` and its composite `claude-code-runner` action add on top — trigger, base-only checkout, pre-staged `tmp/` artifacts, cleanup and dismissal steps, prompt, system-prompt append, tool allowlist, MCP config, model — and the table of this skill's deliberate divergences. |
| `runs/run-<id>.log` | Production run log used as the fixture: the head of `gh run view <id> --log` through the inner CLI's `"subtype": "init"` record, with the `review<TAB>UNKNOWN STEP<TAB><timestamp>` prefixes stripped. |
| `validate.sh` | Five checks of the fixture against `scripts/repro.sh` and `prompt-templates/`: user prompt, system-prompt append and model byte-exact; allowed tools equal modulo the two documented divergences (no GitHub MCP tools here, `Bash(gh api graphql*)` added); MCP server names equal. Exit 0 only on 5/5. |

## When validate.sh fails

Upstream `claude-code-action` (or `claude-pr-review.yml`) shipped a change. To restore equivalence:

1. Capture a fresh successful run: `gh run view <id> -R shader-slang/slang --log`, strip the log prefixes, keep the head through the `"subtype": "init"` record, save as `reference/runs/run-<id>.log` (the lock file has the recipe). Check that secrets are masked (`***`) before committing.
2. Update `prompt-templates/*` and `scripts/repro.sh` (the prompt heredoc and the `ALLOWED` list) to the new bytes; a new production tool that is not a GitHub MCP tool belongs in `ALLOWED` too.
3. Update `instructions.md` and `instructions-overlay.md` to describe what changed.
4. Bump `claude-code-action.lock` (sha, ref, run, `claude_code_version`, `model`).
5. Re-run `validate.sh`; the PR lands when it reports 5/5.

The validator deliberately does not cover the posting side (the trailer, `post-review.sh`) or the inner CLI's version, which the NanoClaw image pins.
