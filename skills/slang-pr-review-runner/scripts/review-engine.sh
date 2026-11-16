#!/usr/bin/env bash
# Choose the program that runs the inner reviewer. Sourced by compose-and-run.sh,
# repro.sh and install.sh here, and by the clarity runner (Reviewer C), so both
# reviewers always pick the same program.
#
# A NanoClaw container states its group's model policy in NANOCLAW_MODEL_WEIGHTS
# (src/model-policy.ts, modelPolicyEnv). A group with weights=open may call
# open-weights models only, so its reviews run on OpenCode with the group's own
# model (OPENCODE_MODEL); every other environment keeps the `claude` CLI that
# mirrors the production review. There is no override: an open-weights group
# never falls back to Claude Code, and a missing `opencode` is an error.
#
# Consider an open-weights slang-reviewer container: NANOCLAW_MODEL_WEIGHTS=open
# and OPENCODE_MODEL=openai/nvidia/zai-org/glm-5.3, so review_engine prints
# "opencode" and scripts/opencode-review.py runs the prompt on GLM. In a closed
# group (eval) or on a developer machine the variable is unset or "any", and
# review_engine prints "claude".

# Print the engine for this environment: "opencode" or "claude".
review_engine() {
  if [ "${NANOCLAW_MODEL_WEIGHTS:-}" = "open" ]; then
    echo opencode
  else
    echo claude
  fi
}

# Succeed when $1, a value given with --model, names the group's OpenCode model,
# with or without OpenCode's provider prefix: for OPENCODE_MODEL=
# openai/nvidia/zai-org/glm-5.3 both `openai/nvidia/zai-org/glm-5.3` and
# `nvidia/zai-org/glm-5.3` match. An open-weights review always runs on the
# group's model, so any other value is refused rather than silently replaced.
is_group_open_model() {
  [ -n "${OPENCODE_MODEL:-}" ] || return 1
  [ "$1" = "$OPENCODE_MODEL" ] || [ "${OPENCODE_PROVIDER:-anthropic}/$1" = "$OPENCODE_MODEL" ]
}

# Exit with a message unless the CLI that `review_engine` chose is on PATH and,
# for OpenCode, the group's model is known. $1 names the installer to suggest.
require_review_engine() {
  local installer="${1:-install.sh}"
  case "$(review_engine)" in
    opencode)
      command -v opencode >/dev/null 2>&1 || {
        echo "error: this group is open-weights (NANOCLAW_MODEL_WEIGHTS=open) and needs the opencode CLI, which is not on PATH. Claude Code is not used for open-weights groups." >&2
        exit 1
      }
      [ -n "${OPENCODE_MODEL:-}" ] || {
        echo "error: this group is open-weights (NANOCLAW_MODEL_WEIGHTS=open) but OPENCODE_MODEL is not set, so the group's model is unknown." >&2
        exit 1
      }
      ;;
    *)
      command -v claude >/dev/null 2>&1 || {
        echo "error: claude CLI not in PATH. Run $installer." >&2
        exit 1
      }
      ;;
  esac
}
