#!/usr/bin/env bash
# Print a Claude Code `--settings` JSON object that excludes every CLAUDE.md
# that lives ABOVE the review checkout, so the inner `claude --print` sees only
# the checkout's own instructions — exactly what the production GitHub Action
# sees, where the checkout has no parents carrying instructions.
#
# Why this exists: Claude Code loads CLAUDE.md / CLAUDE.local.md from the cwd
# and from every parent directory up to /. Inside a NanoClaw container the
# checkout sits at /workspace/agent/slang, and /workspace/agent/CLAUDE.md is the
# coworker document (NanoClaw tooling, scheduling, messaging and routing rules).
# Without the exclude, the inner reviewer and each of its six subagents start
# with ~19K tokens of coworker instructions that do not apply to a PR reviewer
# and partly conflict with REVIEW.md (probe 2026-10-14: 67K → 48K tokens before
# the first output token). Nothing inside the checkout is excluded, so the
# repo's CLAUDE.md, its imports and .claude/agents/* still load.
#
# Usage: claude-md-excludes.sh <repo_root>
#   → {"claudeMdExcludes":["/workspace/agent/CLAUDE.md", ...]}
set -euo pipefail

ROOT="${1:?usage: claude-md-excludes.sh <repo_root>}"
[ -d "$ROOT" ] || { echo "error: $ROOT is not a directory" >&2; exit 1; }

# Resolve symlinks: Claude Code matches the patterns against the absolute
# physical paths it discovered, which are the ones the kernel reports for cwd.
dir="$(cd "$ROOT" && pwd -P)"
dir="$(dirname "$dir")"

items=""
while :; do
  for f in CLAUDE.md CLAUDE.local.md .claude/CLAUDE.md; do
    items="$items,\"${dir%/}/$f\""
  done
  [ "$dir" = "/" ] && break
  dir="$(dirname "$dir")"
done

printf '{"claudeMdExcludes":[%s]}\n' "${items#,}"
