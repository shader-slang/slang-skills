---
name: slang-build
license: MIT
description: "Platform-aware build and test instructions for the Slang compiler. Configure CMake, compile, run slang-test, inspect CI."
provides: [code.build, test.run, test.gen, ci.inspect]
allowed-tools: Bash(git:*), Bash(cmake:*), Bash(python:*), Bash(ninja:*), Read, Grep, Glob
---

# Slang Build

**For**: Building and testing the Slang compiler on any supported platform.

**Usage**: Referenced by other skills. Can also be invoked directly: `/slang-build [debug|release]`

## Step 1: Detect Platform

```bash
case "$(uname -s)" in
  Darwin)  PLATFORM="macos" ;;
  Linux)   PLATFORM="linux" ;;
  MINGW*|MSYS*|CYGWIN*) PLATFORM="windows" ;;
  *)       PLATFORM="unknown" ;;
esac
if grep -qi microsoft /proc/version 2>/dev/null; then PLATFORM="wsl"; fi
```

### Platform Capabilities

| Capability | macOS | Linux | Windows | WSL |
|-----------|-------|-------|---------|-----|
| CPU tests | yes | yes | yes | yes |
| Vulkan | limited | yes | yes | yes |
| CUDA | no | yes | yes | yes |
| D3D12 | no | no | yes | yes |
| Metal | yes | no | no | no |
| SPIRV validation | yes | yes | yes | yes |

On macOS, CUDA and D3D tests are **skipped**, not failed. Check skip counts.

## Step 2: Prerequisites

**Check all before building.** Request missing packages in a single `install_packages` call — the container rebuilds and you must restart from scratch.

Required apt packages (Linux):
- `cmake`, `ninja-build` — build system
- `python3`, `python3-dev` — Python bindings and scripting
- `libssl-dev` — HTTPS operations (CMake FetchContent)

Optional: `clang`, `llvm` (for `-DSLANG_ENABLE_LLVM=ON`)

```bash
for pkg in cmake ninja-build python3 python3-dev libssl-dev; do
  dpkg -l "$pkg" 2>/dev/null | grep -q "^ii" || echo "MISSING: $pkg"
done
```

## Step 3: Initialize Submodules

```bash
git submodule update --init --recursive
```

## Step 4: Configure

```bash
cmake --preset default
```

On Windows (non-WSL): `cmake.exe --preset vs2022 -DSLANG_IGNORE_ABORT_MSG=ON`

### sccache

Pass `-DSLANG_USE_SCCACHE=ON` for faster rebuilds. **Pitfall**: sccache may return cached objects without your debug output. Fix: `SCCACHE_RECACHE=1 cmake --build ...` or reconfigure with `-DSLANG_USE_SCCACHE=OFF`.

## Step 5: Build

### Preset Selection

| Use Case | Preset | Binary Path |
|----------|--------|-------------|
| General development | `releaseWithDebugInfo` | `build/RelWithDebInfo/bin/` |
| Bug investigation | `debug` | `build/Debug/bin/` |
| Performance testing | `release` | `build/Release/bin/` |

### Build Commands

Redirect output to save tokens; re-run on failure for actual errors:

```bash
cmake --build --preset debug --target slangc slang-test \
  >/dev/null 2>&1 || cmake --build --preset debug --target slangc slang-test
```

### WSL Notes

Append `.exe` to host tools: `cmake.exe`, `python.exe`, `gh.exe`.

## Step 6: Test

slang-test must run from the repository root.

```bash
# All tests (multi-server, 10-30 min)
./build/Release/bin/slang-test -use-test-server -server-count 8

# Specific test file
./build/Release/bin/slang-test tests/path/to/test.slang

# Unit tests
./build/Release/bin/slang-test slang-unit-test-tool/
```

**Test directives**:
- CPU compute: `//TEST:COMPARE_COMPUTE(filecheck-buffer=CHECK):-cpu -output-using-type`
- GPU compute: `//TEST:COMPARE_COMPUTE(filecheck-buffer=CHECK):-dx12 -output-using-type`
- Interpreter: `//TEST:INTERPRET(filecheck=CHECK):`
- Diagnostic: `//DIAGNOSTIC_TEST:SIMPLE(diag=CHECK):-target spirv`

**SPIRV validation**: Set `SLANG_RUN_SPIRV_VALIDATION=1` with `slangc -target spirv`. Do not use the system's `spirv-val`.

## Debugging Tools

**IR Dump**: Always combine `-dump-ir` with `-target` and `-o`.

```bash
slangc -dump-ir -target spirv-asm -o tmp.spv test.slang | python extras/split-ir-dump.py
slangc -dump-ir-before lowerGenerics -dump-ir-after lowerGenerics -target spirv-asm -o tmp.spv test.slang > pass.dump
```

**InstTrace** (trace where a problematic IR instruction was created):

```bash
python3 ./extras/insttrace.py <debugUID> ./build/Debug/bin/slangc tests/my-test.slang -target spirv
```

**RTX Remix shader repro**: `./extras/repro-remix.sh` clones dxvk-remix, replaces Slang with local build, compiles all shaders with SPIRV validation.

**SlangPy compat testing**: Clone `external/slangpy`, build with `CMAKE_ARGS="-DSGL_LOCAL_SLANG=ON -DSGL_LOCAL_SLANG_DIR=../.. -DSGL_LOCAL_SLANG_BUILD_DIR=build/Debug" python -m pip install -e .`

## CI

```bash
gh run list --repo shader-slang/slang --workflow=ci.yml --limit 5
gh run view <run-id> --log-failed
```

## Command Line

Slang uses single dashes for multi-character options: `-help`, `-target spirv`, `-dump-ir`, `-stage compute`. Not double dashes.

## AVOID

Do NOT use: `-dump-ast`, `-dump-intermediate-prefix`, `-dump-intermediates`, `-dump-ir-ids`, `-serial-ir`, `-dump-repro`, `-load-repro`, `-extract-repro`, `-category`, `-api`.

## Quick Reference

```bash
# First time: submodules + configure + build
git submodule update --init --recursive && \
cmake --preset default && \
cmake --build --preset releaseWithDebugInfo --target slangc slang-test \
  >/dev/null 2>&1 || cmake --build --preset releaseWithDebugInfo --target slangc slang-test

# Rebuild (already configured)
cmake --build --preset releaseWithDebugInfo --target slangc slang-test \
  >/dev/null 2>&1 || cmake --build --preset releaseWithDebugInfo --target slangc slang-test
```
