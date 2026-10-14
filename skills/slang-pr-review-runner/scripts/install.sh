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

# claude CLI — the inner reviewer runs the version the NanoClaw image pins and
# tests, so we only install one when the environment has none (dev machines).
# A floating `npm install` here previously made the inner CLI track npm's
# latest release independently of the platform image.
if command -v claude >/dev/null 2>&1; then
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

# gh auth (read-only — needed for `gh pr diff` etc. in pr/branch modes)
if ! gh auth status >/dev/null 2>&1; then
  echo ">>> warning: gh auth not configured — pr/branch modes need a token to read the diff" >&2
else
  echo "    gh auth:             $(gh auth status 2>&1 | grep 'Logged in' | head -1 | sed 's/^[ ]*//')"
fi

echo ">>> install.sh — ready"
