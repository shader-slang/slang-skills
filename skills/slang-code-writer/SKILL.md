---
name: slang-code-writer
license: MIT
description: "Implement changes in the Slang compiler. Edit code, write tests, format, commit."
provides: [code.read, code.edit, test.gen]
allowed-tools: Bash, Read, Write, Edit, Grep, Glob
---

## From project

Drawn from `shader-slang/slang` repository guidance: `AGENTS.md`, `CLAUDE.md`,
`CONTRIBUTING.md`, and `.github/copilot-instructions.md`. When working inside the Slang
repository, also consult any repository-local skills under `.claude/skills/` if the user's workflow
matches one of those skills.

## Project layout

Slang is a shading-language compiler and runtime implemented primarily in C++20 and built with
CMake.

Key directories:

- `source/`: core implementation, including `source/slang/`, `source/core/`,
  `source/compiler-core/`, and tools like `source/slangc/`.
- `include/`: public API headers.
- `prelude/` and `source/standard-modules/`: standard/prelude headers.
- `tests/`: test suites grouped by feature or target.
- `tools/`: test infrastructure and developer tools.
- `docs/`: documentation.
- `examples/`: runnable samples.
- `cmake/`: CMake helpers.
- `external/`: vendored dependencies.

## WSL and Windows tooling

When working in this repository from WSL on Windows, use Windows-native developer tools by default
unless the user explicitly asks for the WSL/Linux version.

- Use `git.exe`, not bare `git`. These worktrees use Windows path conventions; WSL Git can corrupt
  or misinterpret worktree state, and Windows Git has much better file I/O performance on this
  checkout.
- When invoking CMake for Windows-hosted builds, use `cmake.exe`, not bare `cmake`, so Visual Studio
  presets and toolchains are found correctly.
- Use `gh.exe` instead of bare `gh` when GitHub CLI commands need to share the same Windows-native
  Git and credential context.
- Convert WSL paths before passing them to Windows tools, for example `wslpath -w "$path"`. Convert
  paths printed by Windows tools back before using them in shell commands, for example
  `wslpath -u "$win_path"`.
- If a required `.exe` tool is unavailable, stop and report it instead of silently falling back to
  the WSL/Linux tool.

## Build and test workflow

Slang build setup is platform-specific, especially under WSL. For compiler builds, use the
`slang-build` skill from `shader-slang/slang-skills` instead of following hard-coded generic CMake
commands. If the skill is unavailable because skills cannot be installed or network access is
limited, use `docs/building.md` as the fallback build reference.

Examples:

- `/slang-build build debug`: build the Debug configuration.
- `/slang-build rebuild debug`: discard the existing build directory and rebuild Debug.
- `/slang-build configure releasewithdebug`: configure an optimized build with symbols.
- `/slang-build clean`: rename and remove the existing build directory.

Do not infer WSL build commands from generic Linux instructions. Follow the platform detection,
host-tool selection, CMake preset choice, and clean-build steps defined by the skill.

After building, run tests from the repository root using the generated `slang-test` binary in the
directory for the selected configuration:

- `build/Debug/bin/slang-test`: run the Debug test suite.
- `build/RelWithDebInfo/bin/slang-test -use-test-server -server-count 8`: run optimized tests with
  symbols in parallel using test servers.
- `build/Release/bin/slang-test -use-test-server -server-count 8`: run Release tests in parallel
  using test servers.

On Windows-hosted builds, use the `.exe` suffix if that is the generated binary name.

## Include path conventions

Prefer direct paths over relative traversal in `#include` directives. The `source/` directory is on
the compiler include path, exposed by the `core` CMake target, so cross-module headers are reachable
without `../`:

```cpp
// Preferred in new code
#include "core/slang-string.h"
#include "compiler-core/slang-source-loc.h"

// Existing code still uses the relative form; do not change it purely for style
#include "../core/slang-string.h"
#include "../compiler-core/slang-source-loc.h"
```

New files should use direct paths. Existing files need not be converted purely for style, but may be
opportunistically updated when the file is already being substantially modified for other reasons.

## Code style

Follow Slang coding conventions (`docs/design/coding-conventions.md`):

- Use four-space indentation for C, C++, headers, and Slang files.
- Run `./extras/formatting.sh` before committing to apply rules from `.clang-format` and
  `.editorconfig`.
- Follow Allman braces, a 100-column limit, left-aligned pointers, and final newlines.
- Avoid STL containers, iostreams, RTTI, and exceptions for ordinary errors.
- Use `<stdio.h>` rather than `<cstdio>`.
- Types: `UpperCamelCase`. Values: `lowerCamelCase`. Macros: `SLANG_SCREAMING_SNAKE`.
- Globals: `g` prefix. Static class members: `s` prefix. Constants: `k` prefix. Members: `m_`
  prefix. Private member functions: `_` prefix.
- Do not use type-based prefixes such as `p` for pointers.
- Function params: `in`, `out`, or `io` prefix for pointer/reference direction.
- Prefer trailing commas in array initializer lists.
- Function names should reflect the nature of the behavior they implement, including important
  return-type or reference semantics, rather than the narrow use case that motivated the function.

## Comments and explanations

Comments should explain why code exists and should help reviewers understand the invariant being
maintained.

- Comment functions in complete sentences: what the function does first, then why if non-obvious.
  Include a concrete example for non-trivial logic.
- Use conversational examples in code comments and PR descriptions. Prefer "Consider this example:"
  followed by the relevant user code over abstract labels such as "Full source shape", "AST trace",
  or "IR trace".
- After the example, explain what happens step by step in natural prose: which producer creates the
  AST/IR/value shape, what invariant this code preserves, and which downstream consumer relies on
  it. Include enough original user code for the example to be understood without reconstructing the
  surrounding program from memory.
- State the implicit contract: assumptions or preconditions, the source of truth or existing
  mechanism being relied on, and why the code sits at this layer.
- Use existing codebase terminology and names. Do not invent new terms for concepts that already
  have names in nearby code, generated modules, diagnostics, IR ops, or design docs.
- Keep comments synchronized with nearby control flow. If a new block runs before the old fallback,
  update surrounding comments so they describe the order the reader sees in the code.

## Review conventions

Recurring review feedback distilled into rules:

- Reuse before you write. Check shared headers such as `slang-ast-type.h`, `slang-ir-util.h`, and
  the `*-util.h` files for existing helpers before adding one.
- When logic is genuinely new, extract it into a named, documented helper rather than an inline
  lambda or long inline block.
- Keep one source of truth for a mapping or classification, and delete any branch or fallback a
  refactor makes unreachable.
- Do not create a second AST/IR/`Val` representation of a value that already has one; multiple
  spellings break `equals`, identity checks, and deduplication. Assert invariants at construction
  sites.
- Use `SLANG_RELEASE_ASSERT` on out-of-contract input instead of silently returning a default.

## Shell script compatibility

Scripts under `extras/` and other repository shell scripts must run on bash 3.2, the version Apple
ships as `/bin/bash` on macOS.

Avoid bash 4+ features such as:

- `${var,,}` or `${var^^}` case conversion.
- Associative arrays (`declare -A`).
- `mapfile` or `readarray`.
- Namerefs (`local -n`).
- Negative array indices.

Prefer portable equivalents, for example lowercase with `tr '[:upper:]' '[:lower:]'`. Validate
scripts with `bash -n script.sh` under the system bash.

## Testing guidelines

Add tests near related coverage in `tests/`.

Slang tests use leading directives such as `//TEST(smoke):SIMPLE:`. Use `//DISABLE_TEST` only with a
clear reason. For targeted runs, pass a prefix, for example:

```bash
build/Debug/bin/slang-test tests/diagnostics/my-test
```

Unit tests live under `tools/slang-unit-test` and typically use `SLANG_UNIT_TEST(name)`.

Common no-GPU patterns:

```slang
//TEST:COMPARE_COMPUTE(filecheck-buffer=CHECK):-cpu -output-using-type
// ... shader code ...
//CHECK: expected_output
```

```slang
//TEST:INTERPRET(filecheck=CHECK):
void main()
{
    //CHECK: hello!
    printf("hello!");
}
```

Diagnostic tests verify compiler errors:

```slang
//DIAGNOSTIC_TEST:SIMPLE(diag=CHECK):-target spirv
int foo = undefined;
//CHECK: E01234
//CHECK:  ^^^^^^^^^ error
```

## Public API constraints

All files under `include/` are public API. Changes must preserve binary and source compatibility for
callers compiled against older versions of the header.

Enums:

- Never insert a new enumerator in the middle of an existing enum.
- Always append new enumerators immediately before the terminal count/sentinel member, assigning an
  explicit integer value when appropriate.
- Removed enumerators should be renamed to `REMOVED_<Name>` and keep the original integer value.
  Never reuse a retired integer.

COM-style interfaces:

- Never reorder virtual methods.
- Never change a virtual method's signature.
- Never insert a new virtual method in the middle of an interface; append only at the end.
- Never remove a virtual method; replace its body with a stub such as `SLANG_E_NOT_IMPLEMENTED` and
  keep the declaration in place.
- Prefer a new derived/versioned interface with its own UUID when extending public COM interfaces
  that clients may implement or query by UUID.

## Problem-solving methodology

Follow the principled path, not the minimal-edit-distance path.

- Fix root causes, not symptoms. A bug surfacing in emit/codegen is usually caused upstream by an IR
  pass, lowering, type legalization, specialization, or the AST/IR representation.
- Question every change. If you cannot name a test that fails without a change, it probably should
  not exist. Ask whether the problem is telling you the direction or representation is flawed.
- Do not mask. A guard, null-check, or special case that papers over malformed AST/IR/witness-table
  data is a band-aid hiding a representation bug. Make the representation correct so consumers stay
  simple.
- Interrogate the input shape. For any code that handles a particular AST node, IR inst, witness,
  type, or similar shape, ask whether that shape is correct and principled, or whether the upstream
  producer should be fixed. Handle it locally only when the shape is genuinely valid input.
- Address conceptually unordered key-to-value data, such as witness-table or interface requirement
  entries, by role/key, never by position/index.
- Keep a working log while investigating: the problem and motivating example, cascading issues, the
  fix chosen for each and why it is principled, and rejected alternatives. Distill this into the PR
  description; do not commit the scratch log.

## Self-review for unprincipled changes

Before finalizing a non-trivial compiler change, review the diff for signs that the fix is
compensating for a bad AST/IR/`Val`/witness representation. Treat the following patterns as
high-risk until you can prove they are the right layer:

- A new custom equivalence relation over `DeclRef`, `Val`, `Type`, `Witness`, or IR shapes, such as
  recursive helpers named like `are...Equivalent`, `does...Match`, or `try...Match`. First ask why
  normal `substitute`, `resolve`, `getCanonicalType`, `equals`, or an existing canonical builder
  does not already make the two values identical.
- A new helper, fallback, or `try...` function that exists only to make one failing test pass. Audit
  every new helper, even small ones: if it redoes substitution, resolution, AST copy, generic
  solving, lookup, or lowering, it is probably hiding the actual invariant break.
- Code that converts checked semantic data back into syntax, such as rebuilding an `Expr` or
  `TypeExp` from a `Val`, `Type`, `DeclRef`, or witness. The checked semantic field should usually
  remain the source of truth.
- Code that walks arbitrary operand graphs, substitution chains, witness chains, lookup paths, or
  IR users to rediscover context such as generic arguments, requirement keys, canonical paths, or
  parent declarations. The producer should usually store or construct the canonical form directly.
- Lowering, emit, specialization, typeflow, or backend logic that patches a malformed AST/IR shape
  from an earlier phase. These consumers should be simple; if they need front-end-specific
  knowledge of a representation accident, trace the producer instead.
- Hardcoded knowledge of particular `DeclRef` subclasses, builtin magic type names, generic
  argument indices, witness-table entry order, or nested-vs-flat specialization shape. Such code
  needs a strong invariant and should usually live at a canonical construction boundary.
- Guards that silently return a default value for an impossible shape. Use an assertion when the
  shape is truly out of contract; otherwise explain why the shape is valid input and add coverage.

Start each review by making a short inventory of every new helper, fallback, and special case in the
diff. For each flagged change, answer:

1. What exact shape reaches this code? Include a concrete example and the producing function.
2. Is that shape canonical and intentionally allowed, or an accidental alternative spelling?
3. If it is accidental, can the producer be fixed so downstream code uses the existing
   `substitute`/`resolve`/canonicalization path?
4. What semantic source of truth already exists, and is this code rebuilding syntax or structure
   from it instead of preserving it?
5. Which test fails if this change is removed, and does that test prove this layer is responsible?
   Do the revert drill when practical.
6. Can the special case be replaced by an assertion plus a producer-side fix, or by reusing an
   existing helper?

Do not keep a flagged change merely because it makes tests pass. If it remains necessary, the
`Process report` section of the PR description must justify why this input shape is valid and why
this layer owns the logic, with a code trace from producer to consumer.

## Development workflow

Adding a new language feature usually involves:

1. Update lexer for new tokens (`source/compiler-core/slang-lexer.cpp`).
2. Extend parser for new syntax (`source/slang/slang-parser.cpp`).
3. Add semantic analysis (`source/slang/slang-check-*.cpp`).
4. Implement IR generation (`source/slang/slang-ir-*.cpp`).
5. Add code generation for each target backend (`source/slang/slang-emit-*.cpp`).
6. Write comprehensive tests under `tests/`.

Other common tasks:

- Adding an IR instruction: update `source/slang/slang-ir-insts.lua`, then regenerate generated
  sources as required by the build.
- Adding a built-in function: add it to the appropriate module in `prelude/`.
- Adding a new target: implement the relevant emitter in `source/slang/slang-emit-*.cpp`.

## Commit and PR workflow

- Use short, imperative commit subjects, for example `Reject invalid descriptor heap access`.
- Do not mention Claude in commit messages.
- Keep PRs small and based on `master`.
- PRs require passing workflows, review approval, and a `pr: non-breaking` or `pr: breaking change`
  label.
- For formatting failures, run installed hooks from `./extras/install-git-hooks.sh` or request the
  format bot with `/format`.

Write PR descriptions in this five-part format:

1. **Motivation** - the problem, with a concrete example or motivating test case.
2. **Proposed solution** - the approach and why it is principled.
3. **Change summary** - the files/areas touched and what each does.
4. **Concepts and vocabulary** - a short glossary between the change summary and the process
   report. Restate only codebase-specific or subtle terms the report relies on.
5. **Process report** - explain every change with a logical reason. For a cascading issue, describe
   the issue with its motivating test case and justify the fix with a code trace naming the exact
   functions or IR instructions involved. For any change that handles, guards, or special-cases a
   particular input shape, answer whether that shape is correct and principled or whether its
   producer should have been fixed.

Write for a reviewer without the full context in their head. Use the same conversational style
expected in code comments: start from a concrete user-code example, include the full relevant
snippet rather than just a type or function name, and explain the logical steps in order. Say what
the compiler builds, how that representation flows through named functions or IR instructions, and
why the chosen fix preserves the invariant. Avoid terse headings like "AST trace"; make the prose
read like an explanation to a reviewer who is learning the scenario for the first time.

**Autonomy:** Proceed through format, test, and commit without asking for confirmation. Only stop
and notify the user if tests fail and the failure is not self-fixable.
