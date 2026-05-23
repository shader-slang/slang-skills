---
description: Platform-aware build instructions for the Slang compiler. Use whenever configuring, building, rebuilding, or validating Slang, including regression checks and bisects in a Slang checkout; it can also be invoked explicitly via /slang-build.
license: Apache-2.0
metadata:
    github-path: skills/slang-build
    github-ref: refs/heads/main
    github-repo: https://github.com/shader-slang/slang-skills
    github-tree-sha: 5a1db12cc53abc570c6809bcc43e09a4c7c3918e
name: slang-build
---
# Slang Build

**For**: Building the Slang compiler on any supported platform.

**Usage**: Apply this workflow for Slang compiler configure/build/rebuild/validation work,
including regression checks and bisects. It can also be invoked directly:

```text
/slang-build [action] [config] [host]

  action  build (default) | rebuild | clean | configure
  config  debug (default) | release | releasewithdebug
  host    native (default) | windows | linux
```

## Parse Arguments

At the start of every invocation, parse the arguments to determine the action and build
configuration, and host. All are optional and order-independent. `native` means the preferred
developer build for the current environment; on WSL, that is the native Windows build.

```bash
ACTION="build"
CONFIG="debug"
BUILD_HOST="native"

for ARG in $ARGUMENTS; do
  ARG_LOWER=$(echo "$ARG" | tr '[:upper:]' '[:lower:]')
  case "$ARG_LOWER" in
    build|rebuild|clean|configure) ACTION="$ARG_LOWER" ;;
    debug|release|releasewithdebug) CONFIG="$ARG_LOWER" ;;
    native|windows|linux) BUILD_HOST="$ARG_LOWER" ;;
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

# Select build host and CMake executable. Prefer the native Windows build from WSL unless
# the user explicitly asks for a Linux build.
if [ "$BUILD_HOST" = "native" ]; then
  if [ "$PLATFORM" = "wsl" ]; then
    BUILD_HOST="windows"
  else
    BUILD_HOST="$PLATFORM"
  fi
fi

if [ "$BUILD_HOST" = "windows" ]; then
  CMAKE="cmake.exe"
else
  CMAKE="cmake"
fi

if [ "$BUILD_HOST" = "windows" ]; then
  CMAKE_CONFIGURE_PRESET="vs2026-dev"
  CMAKE_CONFIGURE_ARGS="-DSLANG_IGNORE_ABORT_MSG=ON -DSLANG_EMBED_CORE_MODULE=OFF"
else
  CMAKE_CONFIGURE_PRESET="default"
  CMAKE_CONFIGURE_ARGS="-DSLANG_EMBED_CORE_MODULE=OFF"
fi
```

### WSL Notes

On WSL, `/slang-build debug` defaults to the native Windows build through `cmake.exe` and the
Visual Studio preset. Use `/slang-build debug linux` only when you explicitly want a Linux/Ninja
build from inside WSL.

When targeting the Windows host from WSL, append `.exe` to host tools:
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
Before skipping configure, make sure the existing cache matches `$BUILD_HOST`; a Linux CMake
cache and a Windows CMake cache are not interchangeable. If the guard below reports a mismatch,
run the **Clean Build** steps and then continue with configure.

```bash
if [ -f build/CMakeCache.txt ]; then
  HOST_MISMATCH=0
  if [ "$BUILD_HOST" = "windows" ] && \
     ! grep -q '^CMAKE_HOST_SYSTEM_NAME:INTERNAL=Windows$' build/CMakeCache.txt; then
    HOST_MISMATCH=1
  elif [ "$BUILD_HOST" = "linux" ] && \
       ! grep -q '^CMAKE_HOST_SYSTEM_NAME:INTERNAL=Linux$' build/CMakeCache.txt; then
    HOST_MISMATCH=1
  elif [ "$BUILD_HOST" = "macos" ] && \
       ! grep -q '^CMAKE_HOST_SYSTEM_NAME:INTERNAL=Darwin$' build/CMakeCache.txt; then
    HOST_MISMATCH=1
  fi

  if [ "$HOST_MISMATCH" = "1" ]; then
    echo "Existing build/ was configured for a different host. Run the Clean Build steps, then configure."
    exit 1
  fi
fi
```

```bash
$CMAKE --preset "$CMAKE_CONFIGURE_PRESET" $CMAKE_CONFIGURE_ARGS
```

For Linux/macOS and explicit WSL Linux builds, use the `default` preset. For Windows and default
WSL builds, use the highest available Visual Studio preset in this order:

1. `vs2026-dev` (preferred)
2. `vs2022-dev`
3. `vs2019-dev`

```bash
$CMAKE --preset vs2026-dev -DSLANG_IGNORE_ABORT_MSG=ON -DSLANG_EMBED_CORE_MODULE=OFF
```

- `-DSLANG_IGNORE_ABORT_MSG=ON` suppresses modal abort dialogs during unattended builds.
- `-DSLANG_EMBED_CORE_MODULE=OFF` skips embedding the core module binary, which gives cleaner stack traces and makes bugs easier to track down.

Stop here if `$ACTION` is `configure`.

### GitHub API Rate Limit

If CMake configuration prints an error about the GitHub API rate limit, resolve it by computing
the release tag for the current commit and passing an explicit binary URL.

First, ensure the release tags are fetched locally:

```bash
$GIT fetch --tags
```

Then compute the tag:

```bash
tagFullVersion="$($GIT describe --tags --match 'v20[2-9][0-9].[0-9]*')"
tagVersion="${tagFullVersion%%-*}"
tag="${tagVersion#v}"
```

Then re-run configure with the `-DSLANG_SLANG_LLVM_BINARY_URL` flag appended:

**Linux / explicit WSL Linux:**
```bash
# append to your configure command:
-DSLANG_SLANG_LLVM_BINARY_URL=https://github.com/shader-slang/slang/releases/download/$tagVersion/slang-$tag-linux-x86_64.zip
```

**Windows / WSL targeting Windows:**
```bash
# append to your configure command:
-DSLANG_SLANG_LLVM_BINARY_URL=https://github.com/shader-slang/slang/releases/download/$tagVersion/slang-$tag-windows-x86_64.zip
```

Full example (Linux):
```bash
$CMAKE --preset default -DSLANG_EMBED_CORE_MODULE=OFF \
  -DSLANG_SLANG_LLVM_BINARY_URL=https://github.com/shader-slang/slang/releases/download/$tagVersion/slang-$tag-linux-x86_64.zip
```

Full example (Windows/WSL):
```bash
$CMAKE --preset vs2026-dev -DSLANG_IGNORE_ABORT_MSG=ON -DSLANG_EMBED_CORE_MODULE=OFF \
  -DSLANG_SLANG_LLVM_BINARY_URL=https://github.com/shader-slang/slang/releases/download/$tagVersion/slang-$tag-windows-x86_64.zip
```

### Optional: sccache

For faster rebuilds, pass `-DSLANG_USE_SCCACHE=ON` at configure time. Requires `sccache` in PATH.

**Debugging pitfall**: When debugging with printf/debug output, sccache may return cached
objects that don't include your changes. If edits seem to have no effect, either:
- Force recache: `SCCACHE_RECACHE=1 $CMAKE --build --preset <preset> --target slangc`
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
$CMAKE --build --preset $CMAKE_BUILD_PRESET --target slangc slang-test \
  >/dev/null 2>&1 || $CMAKE --build --preset $CMAKE_BUILD_PRESET --target slangc slang-test
```

### Action: `rebuild`

Run the **Clean Build** steps (rename `build/`, background delete), then Step 3 (configure),
then the build command above.

### Action: `clean`

Run the **Clean Build** steps only (rename + background delete). Do not configure or build.

The redirect-and-retry pattern avoids wasting LLM tokens on successful build output.
On failure, the second invocation shows the actual errors.

### Build Monitoring and Token Use

A fresh build after `configure`, and any `rebuild`, is a full compile. On typical hardware
(8-core CPU), expect 10-20 minutes; significantly less when sccache is enabled and warm.

The intent is to stay token-efficient while still detecting failures or true hangs. The
guidance below applies when the build is launched in the background; a synchronous
invocation simply blocks until completion and needs no polling.

- After launching a fresh build or rebuild, do not request status/output again for 10-15
  minutes unless the process exits first.
- If the build is still running after that, check at coarse intervals, typically every 2-5
  minutes. Do not poll every few seconds just to confirm activity.
- Prefer the quiet redirect-and-retry command above. Avoid extra `tail`, `ps`, or verbose
  build monitoring unless diagnosing a likely hang after a long interval.

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

### One-liner: configure + build (first time, Linux/macOS or explicit WSL Linux)

```bash
git submodule update --init --recursive && \
cmake --preset default -DSLANG_EMBED_CORE_MODULE=OFF && \
cmake --build --preset $CMAKE_BUILD_PRESET --target slangc slang-test \
  >/dev/null 2>&1 || cmake --build --preset $CMAKE_BUILD_PRESET --target slangc slang-test
```

### One-liner: configure + build (first time, WSL default native Windows / Git Bash)

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
$CMAKE --build --preset $CMAKE_BUILD_PRESET --target slangc slang-test \
  >/dev/null 2>&1 || $CMAKE --build --preset $CMAKE_BUILD_PRESET --target slangc slang-test
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
