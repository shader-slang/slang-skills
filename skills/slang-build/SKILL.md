---
name: slang-build
description: Platform-aware build instructions for the Slang compiler. Only invoke when explicitly called via /slang-build or referenced by other skills.
---

# Slang Build

**For**: Building the Slang compiler on any supported platform.

**Usage**: Referenced by other skills. Can also be invoked directly: `/slang-build [debug|release]`

---

## Step 1: Detect Platform

Detect the current platform and set variables accordingly:

```bash
# Detect OS
case "$(uname -s)" in
  Darwin)  PLATFORM="macos" ;;
  Linux)   PLATFORM="linux" ;;
  MINGW*|MSYS*|CYGWIN*) PLATFORM="windows" ;;
  *)       PLATFORM="unknown" ;;
esac

# Detect WSL
if grep -qi microsoft /proc/version 2>/dev/null; then
  PLATFORM="wsl"
fi
```

### WSL Notes

On WSL, append `.exe` to host tools:
- `git.exe` instead of `git` (if Windows git was used to set up this repo — see detection below)
- `cmake.exe` instead of `cmake`
- `python.exe` instead of `python`
- `gh.exe` instead of `gh`

### Detect git binary (Windows / WSL)

On WSL, both `git` (WSL/Linux git) and `git.exe` (Windows Git for Windows) exist on PATH but
are **not interchangeable**. Whichever was used to clone or init the repo must be used for all
subsequent operations — mixing them corrupts the index regardless of which filesystem the repo
lives on.

Detect by probing which git can actually read the repo:

```bash
GIT="git"
if [ "$PLATFORM" = "wsl" ]; then
  if ! git rev-parse --git-dir > /dev/null 2>&1; then
    if git.exe rev-parse --git-dir > /dev/null 2>&1; then
      GIT="git.exe"
    fi
  fi
fi
# On native Windows (MINGW/MSYS), 'git' already resolves to git.exe — no change needed.
```

Use `$GIT` in place of `git` for all subsequent commands in this session.

### Platform Capabilities

| Capability | macOS | Linux | Windows | WSL |
|-----------|-------|-------|---------|-----|
| CPU tests | yes | yes | yes | yes |
| Vulkan | limited | yes | yes | yes |
| CUDA | no | yes | yes | yes |
| D3D12 | no | no | yes | yes |
| Metal | yes | no | no | no |
| SPIRV validation | yes | yes | yes | yes |

**Important**: On macOS, CUDA and D3D tests will be **skipped**, not failed. A test run
showing all passes with many skips may hide real failures. Always check skip counts.

---

## Step 2: Initialize Submodules

Required before first build:

```bash
$GIT submodule update --init --recursive
```

(`$GIT` is set in Step 1 — `git` on Linux/macOS, `git.exe` on WSL with a Windows-hosted repo.)

---

## Step 3: Configure

```bash
cmake --preset default -DSLANG_EMBED_CORE_MODULE=OFF
```

On Windows (including WSL targeting a Windows build), use the highest available Visual Studio preset in this order:

1. `vs2026-dev` (preferred)
2. `vs2022-dev`
3. `vs2019-dev`

```bash
cmake.exe --preset vs2026-dev -DSLANG_IGNORE_ABORT_MSG=ON -DSLANG_EMBED_CORE_MODULE=OFF
```

- `-DSLANG_IGNORE_ABORT_MSG=ON` suppresses modal abort dialogs during unattended builds.
- `-DSLANG_EMBED_CORE_MODULE=OFF` skips embedding the core module binary, which gives cleaner stack traces and makes bugs easier to track down.

### Optional: sccache

For faster rebuilds, pass `-DSLANG_USE_SCCACHE=ON` at configure time. Requires `sccache` in PATH.

**Debugging pitfall**: When debugging with printf/debug output, sccache may return cached
objects that don't include your changes. If edits seem to have no effect, either:
- Force recache: `SCCACHE_RECACHE=1 cmake --build --preset <preset> --target slangc`
- Or temporarily disable: reconfigure with `-DSLANG_USE_SCCACHE=OFF`

---

## Step 4: Build

### Preset Selection

| Use Case | Preset | Binary Path | When |
|----------|--------|-------------|------|
| **Default** | `debug` | `build/Debug/bin/` | General development — assertions enabled, full debug symbols |
| Performance testing | `releaseWithDebugInfo` | `build/RelWithDebInfo/bin/` | Faster builds when assertions aren't needed |
| CI / benchmarking | `release` | `build/Release/bin/` | Benchmarking, CI-like validation |

**Default**: Use `debug` for general development — assertions are enabled and catch invariant
violations early, which is critical for tracking down bugs.

### Build Commands

```bash
# Build specific targets (preferred — faster than building everything)
cmake --build --preset <preset> --target slangc slang-test \
  >/dev/null 2>&1 || cmake --build --preset <preset> --target slangc slang-test
```

The redirect-and-retry pattern avoids wasting LLM tokens on successful build output.
On failure, the second invocation shows the actual errors.

---

## Step 5: Verify

After building, verify the binaries exist:

```bash
# Adjust path based on preset (default: Debug)
ls build/Debug/bin/slangc
ls build/Debug/bin/slang-test
```

---

## Quick Reference

### One-liner: configure + build (first time, Linux/macOS)

```bash
git submodule update --init --recursive && \
cmake --preset default -DSLANG_EMBED_CORE_MODULE=OFF && \
cmake --build --preset debug --target slangc slang-test \
  >/dev/null 2>&1 || cmake --build --preset debug --target slangc slang-test
```

### One-liner: configure + build (first time, WSL / Git Bash)

```bash
$GIT submodule update --init --recursive && \
cmake.exe --preset vs2026-dev -DSLANG_IGNORE_ABORT_MSG=ON -DSLANG_EMBED_CORE_MODULE=OFF && \
cmake.exe --build --preset debug --target slangc slang-test \
  >/dev/null 2>&1 || cmake.exe --build --preset debug --target slangc slang-test
```

### Configure + build (first time, Windows PowerShell)

```powershell
git submodule update --init --recursive
cmake.exe --preset vs2026-dev -DSLANG_IGNORE_ABORT_MSG=ON -DSLANG_EMBED_CORE_MODULE=OFF
cmake.exe --build --preset debug --target slangc slang-test 2>$null
if ($LASTEXITCODE -ne 0) { cmake.exe --build --preset debug --target slangc slang-test }
```

### One-liner: rebuild (already configured)

```bash
cmake --build --preset debug --target slangc slang-test \
  >/dev/null 2>&1 || cmake --build --preset debug --target slangc slang-test
```
