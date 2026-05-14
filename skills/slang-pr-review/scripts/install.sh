#!/usr/bin/env bash
# Idempotent installer for the slang-pr-review skill.
# Safe to re-run after every container restart.
set -euo pipefail

PREFIX="${PREFIX:-$HOME/.local}"
mkdir -p "$PREFIX/bin"
export PATH="$PREFIX/bin:$PATH"

echo ">>> install.sh — checking dependencies"

# claude CLI
if ! "$PREFIX/bin/claude" --version >/dev/null 2>&1; then
  echo ">>> installing @anthropic-ai/claude-code"
  npm install -g --prefix "$PREFIX" @anthropic-ai/claude-code >/dev/null 2>&1
fi
echo "    claude:              $($PREFIX/bin/claude --version 2>&1 | head -1)"

# github MCP server (only required for --live-on-fork; install regardless)
if [ ! -x "$PREFIX/bin/mcp-server-github" ]; then
  echo ">>> installing @modelcontextprotocol/server-github"
  npm install -g --prefix "$PREFIX" @modelcontextprotocol/server-github >/dev/null 2>&1
fi
echo "    mcp-server-github:   $(test -x $PREFIX/bin/mcp-server-github && echo OK)"

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

# gh auth
if ! gh auth status >/dev/null 2>&1; then
  echo ">>> warning: gh auth not configured — dry-run still works (uses gh pr diff with no token), but --live-on-fork will fail" >&2
else
  echo "    gh auth:             $(gh auth status 2>&1 | grep 'Logged in' | head -1 | sed 's/^[ ]*//')"
fi

echo ">>> install.sh — ready"
