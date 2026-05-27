---
name: slang-sti
description: Install and use sti, a fast parallel test runner that replaces direct slang-test usage with crash recovery, retries, and better output.
argument-hint: "[filter] [--wsl]"
---

# Slang STI (Slang Test Interceptor)

**For**: Running Slang tests faster and more reliably than `slang-test` directly.

**Usage**: `/slang-sti [filter] [--wsl]` or referenced by other skills as a drop-in replacement for `slang-test`.

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

Under WSL, use `git.exe` for the clone by default and stop if it is missing;
only use native WSL `git` when the user explicitly requested a WSL-native run.

```bash
ARGS="${ARGUMENTS:-}"
USE_WSL_TOOLS=false
if printf '%s\n' "$ARGS" | grep -Eq '(^|[[:space:]])--wsl([[:space:]]|$)'; then
  USE_WSL_TOOLS=true
fi
GIT=git
if { [ -n "${WSL_DISTRO_NAME:-}" ] || grep -qi microsoft /proc/version 2>/dev/null; } && [ "$USE_WSL_TOOLS" = false ]; then
  command -v git.exe >/dev/null 2>&1 || { echo "Missing Windows-hosted tool: git.exe"; exit 1; }
  GIT=git.exe
fi
"$GIT" clone https://github.com/expipiplus1/slang-test-interceptor.git
cd slang-test-interceptor
cargo build --release
# Binary: target/release/sti
```

---

## Usage

Run from the Slang repository root. sti auto-detects the newest `slang-test` build.
Under WSL with the default Windows-hosted Slang build, ensure sti is using
`slang-test.exe` from that build. Stop if only a WSL-native `slang-test` is
available; do not use it as a fallback for Windows-hosted validation.

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
2. Verify Slang is built (`ls build/*/bin/slang-test*`). Under WSL default Windows-hosted builds, require `slang-test.exe`. If not, build first (see `slang-build` skill).
3. If `$ARGUMENTS` contains a build type, pass `--build-type <TYPE>`.
4. If `$ARGUMENTS` contains filter patterns, pass them as positional arguments.
5. Run `sti` from the repository root and monitor output.
6. On failure, analyze the grouped diff output to help the user fix issues.
