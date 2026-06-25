---
name: slang-fix-bug
description: Analyze a Slang compiler bug from a test failure, CI log, or GitHub issue. Only invoke when explicitly called via /slang-fix-bug.
argument-hint: "<bug-source> [--parallel N] [--wsl]"
license: Apache-2.0
---

# Slang Bug Fix

**For**: Diagnosing and fixing Slang compiler bugs -- from symptom to root cause to validated fix.

**Core Principle**: Dig into the root cause. Never apply a band-aid fix without understanding
why the bug exists, what invariants are violated, and which producer should have created the
correct representation. Present alternative fix strategies to the user before implementing.

**Principled fix rule**: When you see an assert, crash, ICE, malformed IR, or impossible AST shape,
start by questioning the input shape. Is the AST/IR/witness/type shape valid and intentional? If
not, the fix is usually in the upstream producer, not at the crash site.

**Usage**: `/slang-fix-bug <bug-source> [--parallel N] [--wsl]`

Where `<bug-source>` is one of:
- A GitHub issue number or URL (e.g., `#10419` or `https://github.com/shader-slang/slang/issues/10419`)
- A test file path (e.g., `tests/bugs/my-failing-test.slang`)
- A CI log URL or terminal output
- A description of the symptom

Options:
- `--parallel N`: Launch N parallel fix agents (default: sequential, one at a time)
- `--wsl`: Force native WSL `git`/`gh` when running under WSL. Without it, WSL
  requires Windows-native `git.exe`/`gh.exe` and stops if either is missing.

## Tool Selection

Before running any `git` or `gh` command, initialize selected tools:

```bash
ARGS="${ARGUMENTS:-}"
USE_WSL_TOOLS=false
if printf '%s\n' "$ARGS" | grep -Eq '(^|[[:space:]])--wsl([[:space:]]|$)'; then
  USE_WSL_TOOLS=true
  ARGS="$(printf '%s\n' "$ARGS" | sed -E 's/(^|[[:space:]])--wsl([[:space:]]|$)/ /; s/^[[:space:]]+//; s/[[:space:]]+$//')"
fi

is_wsl() {
  [ -n "${WSL_DISTRO_NAME:-}" ] || grep -qi microsoft /proc/version 2>/dev/null
}

choose_tool() {
  tool="$1"
  if is_wsl && [ "$USE_WSL_TOOLS" = false ]; then
    if command -v "${tool}.exe" >/dev/null 2>&1; then
      printf '%s.exe\n' "$tool"
      return 0
    fi
    printf 'Missing Windows-hosted tool: %s.exe\n' "$tool" >&2
    printf 'Install it on Windows or rerun with --wsl to use native WSL %s.\n' "$tool" >&2
    return 1
  fi

  if command -v "$tool" >/dev/null 2>&1; then
    printf '%s\n' "$tool"
    return 0
  fi
  printf 'Missing native tool: %s\n' "$tool" >&2
  return 1
}

GIT="$(choose_tool git)" || exit 1
GH="$(choose_tool gh)" || exit 1
clean_line() { tr -d '\r'; }
```

Use `$GIT` and `$GH` for all subsequent `git` and `gh` commands.

---

## Principled Fix Methodology

Treat the crash site as evidence, not automatically as the right fix location. A crash in an IR pass
may be caused by ill-formed IR produced during `lower-to-ir`, but the root cause may still be
farther upstream: type checking may have produced an invalid AST shape, a `DeclRef` with missing or
incorrect substitution arguments, the wrong lookup path, an incorrect witness form, or invalid
generic nesting. In some cases the problem may expose a flaw in the language design rather than a
localized implementation bug; stop and ask for a design discussion when the representation itself is
unclear.

Always ask these questions before keeping new logic:

1. Why is this new logic or helper needed? What exact problem is it solving?
2. Why is a new special handling path being added? Is the input pattern valid, or should an upstream
   producer be fixed so this pattern is never produced?
3. If the fix mirrors a pre-existing workaround, is this the right moment to refactor and unify the
   workarounds around a more principled representation?
4. Which test fails without the change, and does that failure prove this layer owns the fix?
5. What existing mechanism should already handle this case, such as `substitute`, `resolve`,
   canonical builders, witness lookup, or generic specialization?

Avoid fixes shaped like `if (A && B && C && D) then do this special thing` merely to make one test
pass. Such predicate ladders are acceptable only when the input shape is valid, the layer owns that
shape, and the PR explanation documents why.

Use conversational explanations in code comments and PR reports. Prefer "Consider this example:"
followed by the relevant user code. Then explain step by step what the compiler builds, which
producer creates the AST/IR/value shape, what invariant the fix preserves, and which downstream
consumer relies on it. Include enough source context that a reviewer can understand the scenario
without reconstructing the surrounding program from memory.

---

## Phase 1: INTAKE -- Understand the Symptom

Gather all available information about the bug from the provided source.

### From a GitHub Issue

```bash
"$GH" issue view <number> --repo shader-slang/slang --json title,body,labels,comments
```

Extract: reproducer code (mandatory), target(s) affected, error message, expected vs actual behavior.

### From a CI Log / Local Test / Description

Parse or ask for: minimal reproducer, target(s), error output.

### Intake Output

Write `tmp/<issue-repository>-<bug-id>/intake.md` so the investigation trail
is preserved for rewinding or handoff.

```markdown
# Bug Intake: [short title]

## Source
[GitHub issue #N / CI log / local test / user description]

## Reproducer
[minimal code + command]

## Error Output
[exact error message, crash output, or wrong behavior]

## Expected Behavior
[what should happen]

## Affected Targets
[spirv, hlsl, cuda, cpu, metal, wgsl, all]

## Initial Classification
- [ ] ICE (Internal Compiler Error / error 99999)
- [ ] Wrong codegen
- [ ] Missing diagnostic
- [ ] SPIRV validation error
- [ ] Crash / segfault / assertion failure
```

---

## Phase 2: ROOT CAUSE INVESTIGATION

### Step 1: Investigate

Run the `slang-investigate` skill on the bug source. This produces `tmp/<bug-id>/investigation.md`
with crash site, code path, violated invariant, design context, and potential fix locations.

See the `slang-investigate` skill for the full investigation methodology.

The investigation must include an input-shape audit. For every assert, crash, or ICE, answer whether
the input AST/IR/witness/type shape reaching the failing code is correct and principled. If the
shape is not valid, trace the producer chain backward. For example, an IR pass might crash on a flat
specialization where nested `IRGeneric` was expected; the right fix may be to correct a frontend
`DeclRef` or witness-table entry so `lower-to-ir` emits the canonical nested specialization instead
of patching the IR pass.

### Step 2: Share investigation (if GitHub issue exists)

**STOP and ask the user** before posting. Show a preview of the comment.

If approved, post an `[Agent]`-prefixed summary of investigation.md to the linked
GitHub issue. This makes the root cause analysis visible to other contributors.

---

## Phase 3: EXPLORE ALTERNATIVES

Decide whether to explore sequentially or in parallel based on the investigation results.

### When to Explore

- **Always** when there are 2+ plausible fix strategies
- **Skip** only when the fix is unambiguous (e.g., a missing case in a switch where the pattern is clear)

### Sequential (default)

Implement and test one strategy at a time. Present results before trying the next.

### Parallel (opt-in with `--parallel N`)

Launch parallel sub-agents in isolated worktrees. Each agent gets its own branch.
Worktrees are created under `.claude/worktrees/` in the repository root
(e.g., `.claude/worktrees/agent-01234567/`), with corresponding git branches.

**Warning**: Parallel agents use significant CPU/memory. On a laptop, 2-3 agents is practical.
On a remote server, up to 5.

### Common Fix Strategies

Strategies are listed best-first. See `slang-investigate` skill for the full ranking rationale.

| Bug Type | Best: IR pass | Acceptable: annotate/reject | Last resort: spot-fix |
|----------|---------------|----------------------------|----------------------|
| Missing validation | Add validation in IR pass | Reject at frontend (semantic) | Guard in emission |
| Wrong codegen | Fix or add the IR pass that transforms | Add new IR pass with annotations | Fix emission logic |
| ICE in pass | Fix the producer so the pass receives canonical input | Reject invalid input earlier (semantic/IR) | Handle a genuinely valid missing case at the crash site |
| Missing lowering | Extend existing lowering pass | Add new lowering pass | Emit diagnostic (unsupported) |

### Constructing the Agent Prompt

**Agent prompts must be self-contained.** Agents cannot read other skills.
The orchestrator must read the following skills and include their content
in each agent's prompt at the marked `{placeholder}` locations:
- `slang-build` → `{slang-build content}` (build commands, preset selection)
- `slang-run-tests` → `{slang-run-tests content}` (test commands, skip detection)
- `slang-write-test` → `{slang-write-test content}` (test syntax reference)
- `slang-create-issue` "Commit Rules" section → `{commit-rules}`

Also include the WSL tool rule in every agent prompt: when running under WSL,
use Windows-native `git.exe`/`gh.exe`, and `slangc.exe`/`slang-test.exe` for
Windows-hosted builds, by default. Stop if any selected tool or binary is
missing; only use native WSL tools/binaries when the user explicitly requested
`--wsl`.

### Agent Prompt Template

```text
You are implementing and testing a fix strategy for a Slang compiler bug.
You are running in an isolated git worktree with your own branch.

## Bug Summary
{intake.md content}

## Root Cause
{investigation.md content}

## Your Strategy: [Strategy Name]
[Description of the specific fix strategy]

## Build Reference
{slang-build content}

## Test Syntax Reference
{slang-write-test content}

## Instructions

1. Implement the fix — minimal diff, follow existing patterns, comments only for non-obvious logic
2. Write a regression test in tests/bugs/ or tests/diagnostics/ or tests/language-feature/
3. Build: use build reference above
4. Validate: run regression test + original reproducer. Do NOT run full test suite — the orchestrator runs it on the winning strategy only
5. Format: ./extras/formatting.sh
6. Commit: {commit-rules}. Message: "Fix [short description]". Do NOT push.

## Principled Fix Requirements

- If the failure is an assert, crash, ICE, or impossible shape, first audit whether the input AST,
  IR, witness, type, `DeclRef`, substitution list, lookup path, or generic nesting is valid.
- Trace malformed input to its producer. Do not patch a consumer with a narrow predicate ladder
  unless the shape is valid and this layer owns it.
- If the fix mirrors a workaround already in the codebase, consider whether the right fix is to
  unify those workarounds behind a canonical representation.
- In the report, use a conversational explanation with full source context. Start with "Consider
  this example:", include the relevant user code, then explain the compiler steps and why the fix is
  principled.

## Report

STRATEGY: [Name]
BRANCH: [branch-name]
COMMIT: [commit-hash]
VERDICT: RECOMMENDED | VIABLE | RISKY | NOT_VIABLE
BUILD: pass | fail
REPRODUCER_FIXED: yes | no
REGRESSION_TEST: pass | fail (test_file: [path])
CHANGES: [files changed, functions modified, lines changed]
CORRECTNESS: [root cause fix / symptom fix / partial fix]
INPUT_SHAPE_AUDIT: [is the input shape valid? if not, which producer must change?]
RISK: [low / medium / high — what could break]
CONCERNS: [any remaining concerns]
```

### Step 1: Write evaluation

Write `tmp/<bug-id>/alternatives.md` comparing strategies so the evaluation
trail is preserved. Also present the comparison in the conversation.

### Step 2: Share alternatives (if GitHub issue exists)

**STOP and ask the user** before posting. Show a preview of the comment.

If approved, post an `[Agent]`-prefixed summary of the alternatives comparison
to the linked GitHub issue.

---

## Phase 4: PRESENT TO USER

**STOP and present the alternatives to the user.** Do not proceed without approval.

Present:
1. **Bug summary**: What's broken and why (2-3 sentences)
2. **Root cause**: The violated invariant and where it happens
3. **Alternatives**: Each strategy with verdict, scope, and risk
4. **Recommendation**: Which approach and why
5. **Design check**: Whether this is a localized implementation bug or needs language-design input
6. **Ask**: Which strategy should be implemented?

---

## Phase 5: IMPLEMENT

After user approval, adopt the chosen strategy or implement fresh.

**Worktree CWD warning**: After agents complete, verify you are in the main repo
(`pwd` should be the project root, not `.claude/worktrees/`). Agent worktrees can
shift CWD if you read their files. Use absolute paths from the main repo root.

### Adopt from Worktree (if Phase 3 produced a passing implementation)

Do NOT cherry-pick — worktree branches share the same base commit, so cherry-pick
produces empty commits or conflicts. Instead, extract the diff and apply it:

```bash
"$GIT" checkout -b fix-<issue-number>-<short-description>
"$GIT" diff master..<winning-agent-branch> -- source/ tests/ | "$GIT" apply
```

**Branch naming**: Always include the GitHub issue number. Example: `fix-10314-global-interface-param-crash`, not `fix-global-interface-param-crash`.

### Implement Fresh (if no clean result from Phase 3)

1. Create branch: `fix-<issue-number>-<short-description>` (e.g., `fix-10314-global-interface-param-crash`)
2. Implement the fix — minimal diff, follow existing patterns
3. Write regression test (see `slang-write-test` skill)
4. Build and validate (see `slang-build` and `slang-run-tests` skills)

Before committing, repeat the input-shape audit from Phase 2. If the implementation added a helper,
fallback, or special path, document why it is needed, why this layer owns it, and why the producer
cannot or should not create a simpler canonical representation.

### Format, Commit, and PR

Follow commit rules from the `slang-create-issue` skill.

```bash
./extras/formatting.sh

"$GIT" add <changed-files>
"$GIT" commit -m "$(cat <<'EOF'
Fix [short description of what was broken]

[1-2 sentences explaining the root cause and the fix approach]
EOF
)"

"$GIT" push -u origin HEAD
```

### Verify Pre-existing Failures

After the full test suite runs, if any tests fail, immediately run the same
failing tests on master to confirm they are pre-existing. Document this in the
PR body: "Tests X, Y, Z also fail on master (pre-existing)."

Create PR using the `slang-create-issue` skill PR format:
- Label: `pr: non-breaking` (default)
- Assignee: `--assignee @me`
- Link to issue: `Fixes #NNNN`
- Include: root cause, approach, alternatives considered, test plan
- Include the input-shape audit and a conversational, full-context explanation. Use concrete source
  examples and step-by-step compiler flow rather than terse labels like "AST trace" or "IR trace".
- Suggest reviewers based on `"$GIT" log --format='%an' -- <changed-files> | sort | uniq -c | sort -rn`

---

## Anti-Patterns

### Investigation

1. **Skipping to a fix**: Do not propose a fix before understanding the root cause.
2. **Grep-and-patch**: Adding a null check without understanding why the null occurred.
3. **Single-strategy tunnel vision**: Always consider at least one alternative.
4. **Emission-layer fixes for IR problems**: Keep emission simple. Prefer IR passes.

### Fix

1. **Band-aid over root cause**: Special case in emission rather than fixing the IR pass.
2. **Overly broad changes**: Refactoring a subsystem when a targeted fix suffices.
3. **Missing regression test**: Every fix must include a test.
4. **Fix without validation**: Always rebuild and run the test suite.
5. **Predicate-ladder workaround**: Adding `if (A && B && C && D)` to recognize one malformed input
   pattern instead of fixing the producer of that pattern.
6. **Mirroring old workarounds**: Copying an existing workaround without asking whether this is the
   moment to replace all instances with a principled representation.
7. **Consumer-side normalization**: Making an IR pass, lowering consumer, or backend repair a
   malformed shape that should have been canonicalized by type checking, AST construction, witness
   synthesis, or `lower-to-ir`.

---

## Decision Rules

### When to Fix vs File an Issue

| Signal | Action |
|--------|--------|
| Root cause clear, fix localized, confident in scope | Fix it |
| Root cause clear but fix touches many subsystems | File issue with analysis, fix if user approves |
| Root cause uncertain | File issue with investigation notes |
| Fix might break other things | File issue, propose fix, ask for review guidance |

---

## Output Structure

```text
tmp/<bug-id>/
├── intake.md              # Phase 1: symptom and reproducer
├── investigation.md       # Phase 2: root cause analysis (from slang-investigate)
├── alternatives.md        # Phase 3: fix strategies compared
└── SUMMARY.md             # Final result after fix is implemented

tests/                     # Regression test (committed)
└── <appropriate-dir>/regression-test.slang
```
