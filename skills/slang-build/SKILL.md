---
name: slang-build
description: Platform-aware build instructions for the Slang compiler. Only invoke when explicitly called via /slang-build or referenced by other skills.
license: Apache-2.0
---

# Slang Build

**For**: Building the Slang compiler on any supported platform.

**Usage**: Referenced by other skills. Can also be invoked directly:

```text
/slang-build [action] [config]

  action  build (default) | rebuild | clean | configure
  config  debug (default) | release | releasewithdebug
```

## Parse Arguments

At the start of every invocation, parse the arguments to determine the action and build
configuration. Both are optional and order-independent.

```bash
ACTION="build"
CONFIG="debug"

for ARG in $ARGUMENTS; do
  ARG_LOWER=$(echo "$ARG" | tr '[:upper:]' '[:lower:]')
  case "$ARG_LOWER" in
    build|rebuild|clean|configure) ACTION="$ARG_LOWER" ;;
    debug|release|releasewithdebug) CONFIG="$ARG_LOWER" ;;
  esac
done

# Map config name to CMake preset and binary path
case "$CONFIG" in
  debug)            CMAKE_BUILD_PRESET="debug";                BIN_PATH="build/Debug/bin" ;;
  release)          CMAKE_BUILD_PRESET="release";              BIN_PATH="build/Release/bin" ;;
  releasewithdebug) CMAKE_BUILD_PRESET="releaseWithDebugInfo"; BIN_PATH="build/RelWithDebInfo/bin" ;;
esac
```

Proceed to Step 1 (platform detection), then jump to the section for `$ACTION`.

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

Run this step for actions `configure`, `build` (first time, no existing `build/`), and `rebuild`
(after the old `build/` has been renamed away). Skip for `build` when `build/` already exists.

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

Stop here if `$ACTION` is `configure`.

### Optional: sccache

For faster rebuilds, pass `-DSLANG_USE_SCCACHE=ON` at configure time. Requires `sccache` in PATH.

**Debugging pitfall**: When debugging with printf/debug output, sccache may return cached
objects that don't include your changes. If edits seem to have no effect, either:
- Force recache: `SCCACHE_RECACHE=1 cmake --build --preset <preset> --target slangc`
- Or temporarily disable: reconfigure with `-DSLANG_USE_SCCACHE=OFF`

---

## Step 4: Build

### Config Reference

| `$CONFIG` | `$CMAKE_BUILD_PRESET` | `$BIN_PATH` | Notes |
|-----------|-----------------------|-------------|-------|
| `debug` *(default)* | `debug` | `build/Debug/bin` | Assertions enabled, full debug symbols |
| `releasewithdebug` | `releaseWithDebugInfo` | `build/RelWithDebInfo/bin` | Faster builds when assertions aren't needed |
| `release` | `release` | `build/Release/bin` | Benchmarking, CI-like validation |

### Action: `build` (default)

If `build/` does not yet exist, run Step 3 (configure) first, then build:

```bash
cmake --build --preset $CMAKE_BUILD_PRESET --target slangc slang-test \
  >/dev/null 2>&1 || cmake --build --preset $CMAKE_BUILD_PRESET --target slangc slang-test
```

### Action: `rebuild`

Run the **Clean Build** steps (rename `build/`, background delete), then Step 3 (configure),
then the build command above.

### Action: `clean`

Run the **Clean Build** steps only (rename + background delete). Do not configure or build.

The redirect-and-retry pattern avoids wasting LLM tokens on successful build output.
On failure, the second invocation shows the actual errors.

---

## Step 5: Verify

After building, verify the binaries exist:

```bash
ls "$BIN_PATH"/slangc*
ls "$BIN_PATH"/slang-test*
```

---

## Quick Reference

Examples below use the defaults (`build`, `debug`). Substitute `$CMAKE_BUILD_PRESET` with
`releaseWithDebugInfo` or `release` as needed.

### One-liner: configure + build (first time, Linux/macOS)

```bash
git submodule update --init --recursive && \
cmake --preset default -DSLANG_EMBED_CORE_MODULE=OFF && \
cmake --build --preset $CMAKE_BUILD_PRESET --target slangc slang-test \
  >/dev/null 2>&1 || cmake --build --preset $CMAKE_BUILD_PRESET --target slangc slang-test
```

### One-liner: configure + build (first time, WSL / Git Bash)

```bash
GIT="${GIT:-git}" && \
$GIT submodule update --init --recursive && \
cmake.exe --preset vs2026-dev -DSLANG_IGNORE_ABORT_MSG=ON -DSLANG_EMBED_CORE_MODULE=OFF && \
cmake.exe --build --preset $CMAKE_BUILD_PRESET --target slangc slang-test \
  >/dev/null 2>&1 || cmake.exe --build --preset $CMAKE_BUILD_PRESET --target slangc slang-test
```

### Configure + build (first time, Windows PowerShell)

```powershell
git submodule update --init --recursive
cmake.exe --preset vs2026-dev -DSLANG_IGNORE_ABORT_MSG=ON -DSLANG_EMBED_CORE_MODULE=OFF
cmake.exe --build --preset $CMAKE_BUILD_PRESET --target slangc slang-test *>$null
if ($LASTEXITCODE -ne 0) { cmake.exe --build --preset $CMAKE_BUILD_PRESET --target slangc slang-test }
```

### One-liner: rebuild (already configured)

```bash
cmake --build --preset $CMAKE_BUILD_PRESET --target slangc slang-test \
  >/dev/null 2>&1 || cmake --build --preset $CMAKE_BUILD_PRESET --target slangc slang-test
```

---

## Clean Build

A clean build discards all cached objects and forces a full recompilation. The preferred approach
is to **rename** the `build/` directory rather than delete it in place, for two reasons:

1. On Windows, open file handles inside `build/` will cause an in-place `rm -rf` to fail
   partway through, leaving a partially-deleted tree. A rename either succeeds atomically or
   fails immediately — there is no partial state.
2. The renamed directory can be deleted in the background, so the new configure+build starts
   without waiting for the slow recursive delete to finish.

### Step A: Rename (bash / WSL / Git Bash)

```bash
if [ ! -d "build" ]; then
  echo "build/ directory does not exist. Nothing to clean."
  exit 0
fi
BUILD_TRASH="build_$(date +%s)_$$"
if mv build "$BUILD_TRASH" 2>/dev/null; then
  echo "Renamed build/ to $BUILD_TRASH"
  rm -rf "$BUILD_TRASH" &
  echo "Background delete started (PID $!)"
else
  echo "ERROR: build/ could not be renamed — it is likely in use. Close any processes" \
       "(debuggers, IDE, running binaries) that have files open inside build/ and retry."
  exit 1
fi
```

### Step A: Rename (Windows PowerShell)

```powershell
if (-not (Test-Path -Path build -PathType Container)) {
    Write-Host "build/ directory does not exist. Nothing to clean."
    exit 0
}
$BuildTrash = "build_$([Guid]::NewGuid().ToString('N'))"
if (Rename-Item -Path build -NewName $BuildTrash -ErrorAction SilentlyContinue) {
    Write-Host "Renamed build/ to $BuildTrash"
    Start-Job { Remove-Item -Recurse -Force $using:BuildTrash } | Out-Null
    Write-Host "Background delete started"
} else {
    Write-Error "ERROR: build\ could not be renamed — it is likely in use. Close any processes (debuggers, IDE, running binaries) that have files open inside build\ and retry."
    exit 1
}
```

### Step B: Reconfigure and rebuild

After the rename succeeds, run the full configure+build sequence from Step 3 and Step 4 as if
building for the first time. Do not skip the configure step — the old `CMakeCache.txt` is gone.
