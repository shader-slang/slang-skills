#!/usr/bin/env bash
# Idempotent installer for the slang-pr-review skill.
# Safe to re-run after every container restart.
set -euo pipefail

PREFIX="${PREFIX:-$HOME/.local}"
mkdir -p "$PREFIX/bin"
# $PREFIX/bin goes AFTER the existing PATH: the claude the NanoClaw image ships
# (/pnpm/claude) must win over anything a previous install.sh run put here.
export PATH="$PATH:$PREFIX/bin"

echo ">>> install.sh — checking dependencies"

# shellcheck source=scripts/review-engine.sh
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/review-engine.sh"

# The inner reviewer's CLI, as review-engine.sh chooses it. An open-weights
# group runs on OpenCode, which the NanoClaw image ships, so nothing is
# installed for it and the claude CLI is not needed. Otherwise the inner
# reviewer runs the claude version the NanoClaw image pins and tests, so we only
# install one when the environment has none (dev machines). A floating
# `npm install` here previously made the inner CLI track npm's latest release
# independently of the platform image.
if [ "$(review_engine)" = "opencode" ]; then
  require_review_engine install.sh
  echo "    opencode:            $(opencode --version 2>&1 | head -1) ($(command -v opencode)), model ${OPENCODE_MODEL}"
elif command -v claude >/dev/null 2>&1; then
  echo "    claude:              $(claude --version 2>&1 | head -1) ($(command -v claude))"
else
  echo ">>> no claude CLI on PATH — installing @anthropic-ai/claude-code into $PREFIX"
  npm install -g --prefix "$PREFIX" @anthropic-ai/claude-code >/dev/null 2>&1
  echo "    claude:              $("$PREFIX/bin/claude" --version 2>&1 | head -1) ($PREFIX/bin/claude)"
fi

# mcp-server-github was previously installed for --live-on-fork (PR-review
# posting via GitHub MCP). That mode has been removed — output now flows
# back to the calling coworker via send_file. We deliberately do NOT
# install mcp-server-github any more, and the dry-run MCP config does not
# reference it.

# slang checkout (depth-50 master)
SLANG_REPO="${SLANG_REPO:-/workspace/agent/slang}"
if [ ! -d "$SLANG_REPO/.git" ]; then
  echo ">>> cloning shader-slang/slang to $SLANG_REPO"
  git clone --depth 50 https://github.com/shader-slang/slang.git "$SLANG_REPO" >/dev/null 2>&1
else
  ( cd "$SLANG_REPO" && git fetch --depth 50 origin master >/dev/null 2>&1 || true )
fi
echo "    slang/ checkout:     $SLANG_REPO ($(cd $SLANG_REPO && git rev-parse --short HEAD))"

# REVIEW.md + .claude/agents must exist (skill reads them live)
[ -f "$SLANG_REPO/REVIEW.md" ] || { echo "error: $SLANG_REPO/REVIEW.md missing — checkout corrupted" >&2; exit 1; }
[ -d "$SLANG_REPO/.claude/agents" ] || { echo "error: $SLANG_REPO/.claude/agents missing" >&2; exit 1; }
echo "    REVIEW.md:           OK"
echo "    .claude/agents/:     $(ls $SLANG_REPO/.claude/agents | wc -l) subagents"

# GitHub read access (needed for `gh pr diff` etc. in pr/branch modes). Read the
# repository itself: `gh auth status` reports only locally stored credentials, so
# it fails behind a credential proxy that injects the token on the wire.
REVIEW_REPO="${REVIEW_REPO:-shader-slang/slang}"
if gh api "repos/$REVIEW_REPO" --jq .id >/dev/null 2>&1; then
  echo "    GitHub read:         OK ($REVIEW_REPO)"
else
  echo ">>> warning: cannot read $REVIEW_REPO on GitHub — pr/branch modes need read access to the diff" >&2
fi

echo ">>> install.sh — ready"
