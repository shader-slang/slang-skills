---
name: slang-run-tests
description: Platform-aware test runner for the Slang compiler. Only invoke when explicitly called via /slang-run-tests or referenced by other skills.
argument-hint: "[test-path|all|new] [--wsl]"
license: Apache-2.0
---

# Slang Run Tests

**For**: Running Slang compiler tests with platform awareness.

**Usage**: Referenced by other skills. Can also be invoked directly: `/slang-run-tests [test-path|all|new] [--wsl]`

Pass a specific `test-path` to run a single test or directory, `all` (or no
path) to run the full suite, or `new` to run only the `.slang` tests added or
modified relative to the default branch.

---

## Running Tests

**Important**: `slang-test` must run from the repository root directory.

Select the compiler and test runner before executing tests:

```bash
ARGS="${ARGUMENTS:-}"
USE_WSL_TOOLS=false
if printf '%s\n' "$ARGS" | grep -Eq '(^|[[:space:]])--wsl([[:space:]]|$)'; then
  USE_WSL_TOOLS=true
fi

# Resolve the positional test-path (everything that is not a flag).
# Two symbolic names are recognized by this skill (not by slang-test):
#   all - the full suite (maps to an empty path; slang-test with no
#         positional argument runs every test).
#   new - only the .slang tests added or modified vs the default branch.
TEST_PATH="$(printf '%s\n' "$ARGS" | tr ' ' '\n' | grep -v '^--' | grep -v '^$' | head -n1)"
case "$TEST_PATH" in
  all)
    TEST_PATH=""
    ;;
  new)
    # Determine the default branch (origin/HEAD), falling back to main.
    DEFAULT_BRANCH="$(git symbolic-ref --quiet --short refs/remotes/origin/HEAD 2>/dev/null | sed 's@^origin/@@')"
    [ -n "$DEFAULT_BRANCH" ] || DEFAULT_BRANCH=main
    BASE="$(git merge-base "$DEFAULT_BRANCH" HEAD 2>/dev/null || echo "$DEFAULT_BRANCH")"
    # New/modified .slang tests = committed + unstaged tracked changes since
    # BASE, plus untracked files in the working tree. slang-test treats each
    # path as a test-name prefix, so multiple paths can be passed at once.
    TEST_PATH="$(
      { git diff --name-only --diff-filter=AMR "$BASE" -- tests/ 2>/dev/null
        git ls-files --others --exclude-standard -- tests/ 2>/dev/null; } \
        | grep -E '\.slang$' | sort -u | tr '\n' ' '
    )"
    if [ -z "$TEST_PATH" ]; then
      echo "No new or modified .slang tests vs $DEFAULT_BRANCH; nothing to run."
      exit 0
    fi
    echo "Running new/modified tests vs $DEFAULT_BRANCH:"
    printf '  %s\n' $TEST_PATH
    ;;
esac

is_wsl() {
  [ -n "${WSL_DISTRO_NAME:-}" ] || grep -qi microsoft /proc/version 2>/dev/null
}

BIN_PATH="${BIN_PATH:-build/Debug/bin}"
if is_wsl && [ "$USE_WSL_TOOLS" = false ]; then
  SLANG_TEST="$BIN_PATH/slang-test.exe"
  SLANGC="$BIN_PATH/slangc.exe"
  [ -f "$SLANG_TEST" ] || { echo "Missing Windows-hosted binary: $SLANG_TEST"; exit 1; }
  [ -f "$SLANGC" ] || { echo "Missing Windows-hosted binary: $SLANGC"; exit 1; }
else
  SLANG_TEST="$BIN_PATH/slang-test"
  SLANGC="$BIN_PATH/slangc"
  [ -f "$SLANG_TEST" ] || { echo "Missing native binary: $SLANG_TEST"; exit 1; }
  [ -f "$SLANGC" ] || { echo "Missing native binary: $SLANGC"; exit 1; }
fi

# Detect the number of available cores/threads for parallel test servers.
if command -v nproc >/dev/null 2>&1; then
  SERVER_COUNT="$(nproc)"
elif command -v sysctl >/dev/null 2>&1 && sysctl -n hw.logicalcpu >/dev/null 2>&1; then
  SERVER_COUNT="$(sysctl -n hw.logicalcpu)"
else
  SERVER_COUNT="$(getconf _NPROCESSORS_ONLN 2>/dev/null || echo 1)"
fi
[ "${SERVER_COUNT:-0}" -ge 1 ] 2>/dev/null || SERVER_COUNT=1
```

Use `$SLANG_TEST` and `$SLANGC` for all subsequent test and compiler commands.

**Important — capture output to a file.** `slang-test` is very verbose (a full
run can be tens of thousands of lines). Do **not** stream that output into the
conversation. Always redirect both stdout and stderr to a log file with `&>`,
then inspect the log with targeted `grep`/`tail` rather than reading it whole.

```bash
# Choose a log location (mktemp keeps runs from clobbering each other).
TEST_LOG="$(mktemp -t slang-test.XXXXXX.log)"

# Run a specific test
"$SLANG_TEST" tests/path/to/test.slang &> "$TEST_LOG"

# Run all tests in a directory
"$SLANG_TEST" tests/language-feature/generics/ &> "$TEST_LOG"

# Run full suite with parallel servers (one per available core/thread).
# TEST_PATH is empty for a full run (no positional argument), or set when a
# specific test/directory was requested.
"$SLANG_TEST" -use-test-server -server-count "$SERVER_COUNT" $TEST_PATH &> "$TEST_LOG"

echo "Full output saved to: $TEST_LOG"
```

When invoked as `/slang-run-tests all` (or with no test path), `TEST_PATH` is
empty and `slang-test` runs the full suite. When invoked as
`/slang-run-tests new`, `TEST_PATH` is the set of `.slang` tests added or
modified versus the default branch (it exits early if there are none). `all` and
`new` are skill-level conveniences; they are **not** arguments `slang-test`
understands, so they are never passed through literally.

### Inspecting the log without reading it whole

Pull only what you need from `$TEST_LOG` instead of dumping the entire file:

```bash
# Summary line (Total / Passed / Failed / Skipped)
grep -E 'Total:.*Passed:.*Failed:' "$TEST_LOG" | tail -n1

# Just the failures
grep -iE 'fail(ed|ure)?' "$TEST_LOG"

# Last few lines if the run aborted
tail -n 20 "$TEST_LOG"
```

Where `<preset>` is `Debug`, `RelWithDebInfo`, or `Release` matching your build (see `slang-build` skill).

### WSL Binary Selection

When running under WSL with the default Windows-hosted build from `slang-build`,
the selected binaries are `slang-test.exe` and `slangc.exe`. If either expected
`.exe` binary is missing, stop and build the selected host configuration. Do not
silently run a WSL-native `slang-test` or `slangc` from a different build. Use
the non-`.exe` binaries only for native Linux/macOS builds or an explicit WSL
Linux build.

---

## Platform-Aware Target Selection

Not all targets work on every platform. Before running tests, know what will actually execute:

| Target flag | macOS | Linux | Windows/WSL |
|-------------|-------|-------|-------------|
| `-cpu` | yes | yes | yes |
| `-vk` | limited | yes | yes |
| `-cuda` | **no** | yes | yes |
| `-dx12` | **no** | **no** | yes |
| `-metal` | yes | **no** | **no** |
| `-wgsl` | yes | yes | yes |

### Critical: Read Every Number in the Summary

After running tests, always check the summary line — and weigh **all** of its
counts, not just one:

```bash
grep -E 'Total:.*Passed:.*Failed:' "$TEST_LOG" | tail -n1
# e.g. Total: 100, Passed: 60, Failed: 0, Skipped: 40
```

- **Failed** — the most immediate and important number. **It must be `0`.** Any
  non-zero failed count means the change is broken; stop and investigate the
  failures (`grep -iE 'fail(ed|ure)?' "$TEST_LOG"`) before doing anything else.
- **Skipped** — **a skipped test is NOT a passed test.** On platforms that lack a
  backend (e.g., macOS + CUDA), `slang-test` silently skips the test and still
  reports overall success, which can hide real problems. If the skip count is
  high relative to total, verify the tests you care about actually ran. For
  target-specific fixes (SPIRV, CUDA, D3D), skipped tests mean **you cannot
  validate locally** — leave it to CI.
- **Passed / Total** — sanity-check that the totals make sense. If `Total` is far
  smaller than expected, the wrong path may have run or the suite never started;
  re-check the invocation and the tail of the log.

When writing new tests for GPU-less environments, prefer `-cpu` or `INTERPRET` test types.

---

## SPIRV Validation

For SPIRV-related work, enable validation:

```bash
SLANG_RUN_SPIRV_VALIDATION=1 "$SLANGC" -target spirv test.slang
```

Do NOT use the system's `spirv-val` tool — it may be outdated. Slang bundles its own.

To see SPIRV output even when validation fails:

```bash
"$SLANGC" -target spirv-asm -skip-spirv-validation test.slang
```

To generate reference SPIRV via GLSL for comparison:

```bash
"$SLANGC" -target spirv-asm -emit-spirv-via-glsl test.slang
```

---

## Test Types at a Glance

| Question | Test Type | GPU Required? |
|----------|-----------|---------------|
| Does this produce correct output? | `COMPARE_COMPUTE` with `-cpu` | No |
| Does this compile to correct target code? | `SIMPLE(filecheck=CHECK)` | No |
| Does this produce the right error? | `DIAGNOSTIC_TEST:SIMPLE(diag=CHECK)` | No |
| Does this run correctly? | `INTERPRET` | No |
| Does this work on GPU backends? | `COMPARE_COMPUTE` with `-vk`/`-cuda`/`-dx12` | Yes |

For test syntax details, see the `slang-write-test` skill.

---

## Troubleshooting

### Test not found
- File must be under `tests/` directory
- Extension must be `.slang`
- Must run from repo root

### All tests skipped
- Check platform capabilities table above
- Use `-cpu` for platform-independent testing

### FileCheck failures
- Run with verbose output to see mismatches
- Check exact whitespace and formatting in CHECK lines

### Binary not found
- Build first: see `slang-build` skill
- Verify preset matches: `ls build/<preset>/bin/slang-test*`
