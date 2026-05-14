# reference/

What the skill must stay byte-equivalent to.

## Layout

| File | Purpose |
|---|---|
| `claude-code-action.lock` | Pinned commit of `anthropics/claude-code-action` that the skill mirrors. |
| `instructions.md` | Verbatim documentation of the action's runtime — what `bun run-claude` sends to the SDK. Generic, no slang specifics. |
| `instructions-overlay.md` | What `shader-slang/slang/.github/workflows/claude-pr-review.yml` adds on top — the user prompt, system-prompt append, tool allowlist, MCP config. The slang-specific overlay. |
| `runs/run-<id>.log` | Known-good production run log used as the byte-match fixture. |
| `validate.sh` | Diffs five extracts (user prompt, system-prompt append, allowed-tools, model, MCP servers) from the run log against the same five extracts from this skill's `prompt-templates/` and `scripts/repro.sh` defaults. Reports a 5/5 byte match or names the field that drifted. |

## When validate.sh fails

Upstream `claude-code-action` (or `claude-pr-review.yml`) shipped a change. To restore byte-equivalence:

1. Pull a fresh successful run log from a recent shader-slang/slang execution of `claude-pr-review.yml`. Save it under `reference/runs/run-<id>.log`.
2. Update `reference/instructions.md` and `reference/instructions-overlay.md` to describe the new prompts/flags.
3. Update `prompt-templates/*` and `scripts/repro.sh`'s ALLOWED_DRYRUN / ALLOWED_LIVE strings to match the new bytes.
4. Bump `reference/claude-code-action.lock`.
5. Re-run `validate.sh`; PR lands when 5/5 byte-match restores.

This is the same approach used during the skill's initial development. See `review_artifacts/instructions/` in shader-slang/slang's repro session if you need a worked example.
