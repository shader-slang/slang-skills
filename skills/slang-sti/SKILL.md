---
name: slang-sti
description: Install and use sti, a fast parallel test runner that replaces direct slang-test usage with crash recovery, retries, and better output.
---

# Slang STI (Slang Test Interceptor)

**For**: Running Slang tests faster and more reliably than `slang-test` directly.

**Usage**: `/slang-sti [filter]` or referenced by other skills as a drop-in replacement for `slang-test`.

---

## Why sti over slang-test

| | `slang-test -j24` | `sti` |
|---|---|---|
| Full suite | 88s | 40s |
| Single dir (`-j1 tests/compute`) | 22.5s | 15.5s |
| Crash mid-run | Aborts entire suite | Identifies crashing test, reschedules the rest |
| Transient failures | Reported as failures | Auto-retried (default: 2 attempts) |
| Output | Raw pass/fail lines | Grouped diffs, ETA, rerun command for failures |

Additional benefits:
- **Timing cache**: Records per-test times so future runs avoid long-tail batches
- **GPU staggering**: Avoids Vulkan context creation contention at startup
- **Auto-detection**: Finds the newest `slang-test` build automatically

---

## Installing sti

Pre-built binaries: <https://github.com/expipiplus1/slang-test-interceptor/releases>

```bash
# Linux x86_64
curl -L https://github.com/expipiplus1/slang-test-interceptor/releases/latest/download/sti-x86_64-unknown-linux-musl.zip -o /tmp/sti.zip
unzip -o /tmp/sti.zip -d /tmp/sti && install /tmp/sti/sti ~/.local/bin/sti

# Linux aarch64
curl -L https://github.com/expipiplus1/slang-test-interceptor/releases/latest/download/sti-aarch64-unknown-linux-musl.zip -o /tmp/sti.zip
unzip -o /tmp/sti.zip -d /tmp/sti && install /tmp/sti/sti ~/.local/bin/sti

# macOS Apple Silicon
curl -L https://github.com/expipiplus1/slang-test-interceptor/releases/latest/download/sti-aarch64-apple-darwin.zip -o /tmp/sti.zip
unzip -o /tmp/sti.zip -d /tmp/sti && install /tmp/sti/sti ~/.local/bin/sti

# macOS x86_64
curl -L https://github.com/expipiplus1/slang-test-interceptor/releases/latest/download/sti-x86_64-apple-darwin.zip -o /tmp/sti.zip
unzip -o /tmp/sti.zip -d /tmp/sti && install /tmp/sti/sti ~/.local/bin/sti

# Windows (PowerShell)
Invoke-WebRequest -Uri https://github.com/expipiplus1/slang-test-interceptor/releases/latest/download/sti-x86_64-pc-windows-msvc.zip -OutFile $env:TEMP\sti.zip
Expand-Archive -Path $env:TEMP\sti.zip -DestinationPath $env:LOCALAPPDATA\sti -Force
# Then add $env:LOCALAPPDATA\sti to PATH
```

Or build from source (requires Rust toolchain):

```bash
git clone https://github.com/expipiplus1/slang-test-interceptor.git
cd slang-test-interceptor
cargo build --release
# Binary: target/release/sti
```

---

## Usage

Run from the Slang repository root. sti auto-detects the newest `slang-test` build.

```bash
sti                              # All tests
sti diagnostic                   # Tests matching "diagnostic" (infix)
sti '^tests/compute'             # Tests matching prefix
sti '^tests/compute' '^tests/autodiff'  # Union of patterns
sti slang-unit-test-tool         # Internal unit tests
sti --build-type release         # Use release build
sti -g 0                         # CPU-only (skip GPU tests)
sti --dry-run diagnostic         # List matching tests without running
```

---

## Key Options

| Option | Description |
|---|---|
| `<FILTERS>` | Regex patterns (union). Empty = all tests |
| `--build-type <TYPE>` | `debug`, `release`, `relwithdebinfo`, `minsizerel` |
| `-j <N>` | Parallel workers (default: CPU count) |
| `-g <N>` | Max concurrent GPU batches. `0` = CPU-only |
| `--retries <N>` | Retries for failures (default: 2) |
| `--dry-run` | List tests without running |
| `--ignore <PATTERN>` | Exclude tests matching regex |
| `--api <API>` | Only run tests for specific APIs (e.g., `vk`, `cuda`) |
| `--ignore-api <API>` | Exclude specific APIs |
| `-v` | Verbose: per-worker progress, slow-test report |

---

## Interactive Workflow

1. Check if `sti` is on PATH (`which sti`). If not, install it (see above).
2. Verify Slang is built (`ls build/*/bin/slang-test`). If not, build first (see `slang-build` skill).
3. If `$ARGUMENTS` contains a build type, pass `--build-type <TYPE>`.
4. If `$ARGUMENTS` contains filter patterns, pass them as positional arguments.
5. Run `sti` from the repository root and monitor output.
6. On failure, analyze the grouped diff output to help the user fix issues.
