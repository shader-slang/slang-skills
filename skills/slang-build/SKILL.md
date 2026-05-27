---
name: slang-build
description: Platform-aware build, test, and CI inspection for the Slang compiler. Use when configuring CMake, compiling slangc/slang-test, running slang-test, inspecting CI runs, or doing regression bisects. Invoke directly via /slang-build.
license: Apache-2.0
provides: [code.build, test.run, test.gen, ci.inspect]
allowed-tools: Bash(git:*), Bash(cmake:*), Bash(python:*), Bash(ninja:*), Read, Grep, Glob
---
 
# Slang Build
 
**For**: Building and testing the Slang compiler on any supported platform.
 
**Usage**: Referenced by other skills, or invoked directly:
 
```text
/slang-build [action] [config] [host]
 
  action  build (default) | rebuild | clean | configure
  config  debug (default) | release | releasewithdebug
  host    native (default) | windows | linux
```
 
`native` = the preferred developer build for the current environment. On WSL, `native` means the Windows build.
 
---
 
## Step 1: Parse Arguments
 
```bash
ACTION="build"
CONFIG="debug"
BUILD_HOST="native"
 
for ARG in $ARGUMENTS; do
  ARG_LOWER=$(echo "$ARG" | tr '[:upper:]' '[:lower:]')
  case "$ARG_LOWER" in
    build|rebuild|clean|configure)   ACTION="$ARG_LOWER" ;;
    debug|release|releasewithdebug)  CONFIG="$ARG_LOWER" ;;
    native|windows|linux)            BUILD_HOST="$ARG_LOWER" ;;
  esac
done
 
case "$CONFIG" in
  debug)            CMAKE_BUILD_PRESET="debug";                BIN_PATH="build/Debug/bin" ;;
  release)          CMAKE_BUILD_PRESET="release";              BIN_PATH="build/Release/bin" ;;
  releasewithdebug) CMAKE_BUILD_PRESET="releaseWithDebugInfo"; BIN_PATH="build/RelWithDebInfo/bin" ;;
esac
```
 
### Config reference
 
| `$CONFIG`              | preset                 | binary path                 | use for                                        |
| ---------------------- | ---------------------- | --------------------------- | ---------------------------------------------- |
| `debug` *(default)*    | `debug`                | `build/Debug/bin`           | Bug investigation. Assertions on, full symbols.|
| `releasewithdebug`     | `releaseWithDebugInfo` | `build/RelWithDebInfo/bin`  | General dev. Faster than debug.                |
| `release`              | `release`              | `build/Release/bin`         | Benchmarking, CI-like validation.              |
 
---
 
## Step 2: Detect Platform and Select Tools
 
```bash
case "$(uname -s)" in
  Darwin)               PLATFORM="macos" ;;
  Linux)                PLATFORM="linux" ;;
  MINGW*|MSYS*|CYGWIN*) PLATFORM="windows" ;;
  *)                    PLATFORM="unknown" ;;
esac
 
if grep -qi microsoft /proc/version 2>/dev/null; then
  PLATFORM="wsl"
fi
 
# Resolve "native" build host.
if [ "$BUILD_HOST" = "native" ]; then
  if [ "$PLATFORM" = "wsl" ]; then
    BUILD_HOST="windows"
  else
    BUILD_HOST="$PLATFORM"
  fi
fi
```
 
### Select tool binaries
 
On WSL, `git` and `git.exe` (and `cmake` / `cmake.exe`) both exist on PATH but are **not interchangeable**. Pick the binary that matches the chosen build host and use it consistently.
 
```bash
require_tool() {
  if command -v "$1" >/dev/null 2>&1; then printf '%s\n' "$1"; return 0; fi
  printf '%s\n' "$2" >&2; return 1
}
 
if [ "$BUILD_HOST" = "windows" ] && [ "$PLATFORM" = "wsl" ]; then
  GIT=$(require_tool git.exe   "Missing git.exe — install Git for Windows or rerun with host=linux.") || exit 1
  CMAKE=$(require_tool cmake.exe "Missing cmake.exe — install CMake on Windows or rerun with host=linux.") || exit 1
  CMAKE_CONFIGURE_PRESET="vs2026-dev"
  CMAKE_CONFIGURE_ARGS="-DSLANG_IGNORE_ABORT_MSG=ON -DSLANG_EMBED_CORE_MODULE=OFF"
elif [ "$BUILD_HOST" = "windows" ]; then
  GIT=$(require_tool git       "Missing git.") || exit 1
  CMAKE=$(require_tool cmake.exe "Missing cmake.exe.") || exit 1
  CMAKE_CONFIGURE_PRESET="vs2026-dev"
  CMAKE_CONFIGURE_ARGS="-DSLANG_IGNORE_ABORT_MSG=ON -DSLANG_EMBED_CORE_MODULE=OFF"
else
  GIT=$(require_tool git   "Missing git.") || exit 1
  CMAKE=$(require_tool cmake "Missing cmake.") || exit 1
  CMAKE_CONFIGURE_PRESET="default"
  CMAKE_CONFIGURE_ARGS="-DSLANG_EMBED_CORE_MODULE=OFF"
fi
```
 
**Preset fallback** for Windows hosts: try `vs2026-dev` first, then `vs2022-dev`, then `vs2019-dev`.
 
**Use `$GIT` and `$CMAKE` everywhere from here on.** Append `.exe` to any other Windows-hosted tool you invoke (`slangc.exe`, `slang-test.exe`, `python.exe`, `gh.exe`).
 
### Configure flags explained
 
- `-DSLANG_IGNORE_ABORT_MSG=ON` — suppresses modal abort dialogs (unattended Windows builds).
- `-DSLANG_EMBED_CORE_MODULE=OFF` — skips embedding the core module binary; cleaner stack traces.
### Platform capabilities
 
| Capability       | macOS   | Linux | Windows | WSL |
| ---------------- | ------- | ----- | ------- | --- |
| CPU tests        | ✓       | ✓     | ✓       | ✓   |
| Vulkan           | limited | ✓     | ✓       | ✓   |
| CUDA             | ✗       | ✓     | ✓       | ✓   |
| D3D12            | ✗       | ✗     | ✓       | ✓   |
| Metal            | ✓       | ✗     | ✗       | ✗   |
| SPIRV validation | ✓       | ✓     | ✓       | ✓   |
 
On macOS, CUDA and D3D tests are **skipped**, not failed. Check skip counts.
 
---
 
## Step 3: Check Prerequisites (Linux/WSL-linux only)
 
```bash
for pkg in cmake ninja-build python3 python3-dev libssl-dev; do
  dpkg -l "$pkg" 2>/dev/null | grep -q "^ii" || echo "MISSING: $pkg"
done
```
 
If anything missing, request all of them in **one** `install_packages` call — the container rebuilds and you'll restart from scratch.
 
Optional: `clang`, `llvm` (for `-DSLANG_ENABLE_LLVM=ON`).
 
---
 
## Step 4: Dispatch by Action
 
```text
clean      → A (clean)                            → done
configure  → B (submodules + configure)           → done
build      → B (if no build/), then C (build)
rebuild    → A (clean), then B, then C
```
 
---
 
### A. Clean
 
Rename `build/` rather than deleting in place. Renames are atomic; in-place deletes on Windows fail mid-tree when files are open.
 
**bash / WSL / Git Bash:**
```bash
if [ ! -d "build" ]; then echo "Nothing to clean."; exit 0; fi
BUILD_TRASH="build_$(date +%s)_$$"
if mv build "$BUILD_TRASH" 2>/dev/null; then
  echo "Renamed build/ to $BUILD_TRASH"
  rm -rf "$BUILD_TRASH" &
  echo "Background delete started (PID $!)"
else
  echo "ERROR: build/ in use. Close debuggers / IDE / running binaries and retry."
  exit 1
fi
```
 
**Windows PowerShell:**
```powershell
if (-not (Test-Path build -PathType Container)) { Write-Host "Nothing to clean."; exit 0 }
$BuildTrash = "build_$([Guid]::NewGuid().ToString('N'))"
if (Rename-Item -Path build -NewName $BuildTrash -ErrorAction SilentlyContinue) {
    Write-Host "Renamed build/ to $BuildTrash"
    Start-Job { Remove-Item -Recurse -Force $using:BuildTrash } | Out-Null
} else {
    Write-Error "build\ in use. Close debuggers / IDE / running binaries and retry."
    exit 1
}
```
 
---
 
### B. Submodules + Configure
 
```bash
$GIT submodule update --init --recursive
```
 
**Host-cache guard** — bail if the existing `build/` was configured for a different host:
 
```bash
if [ -f build/CMakeCache.txt ]; then
  case "$BUILD_HOST" in
    windows) EXPECTED="Windows" ;;
    linux)   EXPECTED="Linux" ;;
    macos)   EXPECTED="Darwin" ;;
  esac
  if ! grep -q "^CMAKE_HOST_SYSTEM_NAME:INTERNAL=$EXPECTED\$" build/CMakeCache.txt; then
    echo "Existing build/ is for a different host. Run action 'clean' first, then retry."
    exit 1
  fi
fi
```
 
**Configure (bash / WSL / Git Bash):**
```bash
$CMAKE --preset "$CMAKE_CONFIGURE_PRESET" $CMAKE_CONFIGURE_ARGS
```
 
**Configure (Windows PowerShell):**
```powershell
cmake.exe --preset vs2026-dev -DSLANG_IGNORE_ABORT_MSG=ON -DSLANG_EMBED_CORE_MODULE=OFF
```
 
#### Fallback: GitHub API rate limit
 
If configure fails with a GitHub API rate-limit error, compute the release tag and pass `SLANG_SLANG_LLVM_BINARY_URL` explicitly:
 
```bash
$GIT fetch --tags
tagFullVersion="$($GIT describe --tags --match 'v20[2-9][0-9].[0-9]*')"
tagVersion="${tagFullVersion%%-*}"
tag="${tagVersion#v}"
 
LINUX_URL="https://github.com/shader-slang/slang/releases/download/$tagVersion/slang-$tag-linux-x86_64.zip"
WIN_URL="https://github.com/shader-slang/slang/releases/download/$tagVersion/slang-$tag-windows-x86_64.zip"
 
# Re-run configure with the URL matching your build host:
$CMAKE --preset "$CMAKE_CONFIGURE_PRESET" $CMAKE_CONFIGURE_ARGS \
  -DSLANG_SLANG_LLVM_BINARY_URL="$WIN_URL"   # or "$LINUX_URL"
```
 
#### Optional: sccache
 
Pass `-DSLANG_USE_SCCACHE=ON` for faster rebuilds.
 
**Pitfall**: sccache can return cached objects that miss local debug changes. If `printf` / IR-dump edits seem to have no effect:
- Force recache: `SCCACHE_RECACHE=1 $CMAKE --build --preset "$CMAKE_BUILD_PRESET" --target slangc`
- Or reconfigure with `-DSLANG_USE_SCCACHE=OFF`.
---
 
### C. Build
 
**bash / WSL / Git Bash:**
```bash
$CMAKE --build --preset "$CMAKE_BUILD_PRESET" --target slangc slang-test \
  >/dev/null 2>&1 || \
$CMAKE --build --preset "$CMAKE_BUILD_PRESET" --target slangc slang-test
```
 
**Windows PowerShell:**
```powershell
cmake.exe --build --preset $CMAKE_BUILD_PRESET --target slangc slang-test *>$null
if ($LASTEXITCODE -ne 0) {
    cmake.exe --build --preset $CMAKE_BUILD_PRESET --target slangc slang-test
}
```
 
The redirect-then-retry pattern keeps successful builds token-quiet; on failure the second run prints the real errors.
 
#### Monitoring a fresh / clean build
 
Fresh and clean builds are full compiles: 10–20 min on an 8-core CPU, less with a warm sccache.
 
- After kicking one off, **don't poll for 10–15 minutes**.
- Still running after that? Check every 2–5 minutes, not seconds.
- Skip `tail`, `ps`, verbose progress checks unless you suspect a hang.
#### Verify outputs
 
```bash
ls "$BIN_PATH"/slangc*
ls "$BIN_PATH"/slang-test*
```
 
On WSL Windows-hosted builds, **require** `slangc.exe` and `slang-test.exe`. If only the non-`.exe` versions exist, stop — they are from a different build.
 
---
 
## Testing
 
`slang-test` must run from the **repository root**.
 
```bash
# All tests, multi-server (10–30 min)
"$BIN_PATH"/slang-test -use-test-server -server-count 8
 
# Specific test file
"$BIN_PATH"/slang-test tests/path/to/test.slang
 
# Unit tests
"$BIN_PATH"/slang-test slang-unit-test-tool/
```
 
### Test directives
 
- CPU compute: `//TEST:COMPARE_COMPUTE(filecheck-buffer=CHECK):-cpu -output-using-type`
- GPU compute: `//TEST:COMPARE_COMPUTE(filecheck-buffer=CHECK):-dx12 -output-using-type`
- Interpreter:  `//TEST:INTERPRET(filecheck=CHECK):`
- Diagnostic:   `//DIAGNOSTIC_TEST:SIMPLE(diag=CHECK):-target spirv`
### SPIRV validation
 
Set `SLANG_RUN_SPIRV_VALIDATION=1` and use `slangc -target spirv`. **Do not** use the system's `spirv-val`.
 
---
 
## Debugging Tools
 
**IR dump** — always combine `-dump-ir` with `-target` and `-o`:
 
```bash
slangc -dump-ir -target spirv-asm -o tmp.spv test.slang | python extras/split-ir-dump.py
slangc -dump-ir-before lowerGenerics -dump-ir-after lowerGenerics \
       -target spirv-asm -o tmp.spv test.slang > pass.dump
```
 
**InstTrace** — trace where a problematic IR instruction was created:
 
```bash
python3 ./extras/insttrace.py <debugUID> ./build/Debug/bin/slangc tests/my-test.slang -target spirv
```
 
**RTX Remix shader repro**: `./extras/repro-remix.sh` clones dxvk-remix, swaps in your local Slang, compiles all shaders with SPIRV validation.
 
**SlangPy compat testing**: clone `external/slangpy`, then:
 
```bash
CMAKE_ARGS="-DSGL_LOCAL_SLANG=ON -DSGL_LOCAL_SLANG_DIR=../.. -DSGL_LOCAL_SLANG_BUILD_DIR=build/Debug" \
  python -m pip install -e .
```
 
---
 
## CI
 
```bash
gh run list --repo shader-slang/slang --workflow=ci.yml --limit 5
gh run view <run-id> --log-failed
```
 
---
 
## CLI Gotchas
 
Slang uses **single dashes** for multi-character options: `-help`, `-target spirv`, `-dump-ir`, `-stage compute`. Not double dashes.
 
**Do NOT use**: `-dump-ast`, `-dump-intermediate-prefix`, `-dump-intermediates`, `-dump-ir-ids`, `-serial-ir`, `-dump-repro`, `-load-repro`, `-extract-repro`, `-category`, `-api`.