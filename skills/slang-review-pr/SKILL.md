---
name: slang-review-pr
description: Review a Slang compiler PR for correctness, evaluate review feedback, implement fixes, and manage review threads. Only invoke when explicitly called via /slang-review-pr.
argument-hint: "<PR URL or number> [--wsl]"
license: Apache-2.0
---

# Slang PR Review

**For**: Reviewing PRs on the shader-slang/slang repository, evaluating whether the solution
fixes the root cause optimally, addressing review feedback, and managing review threads.

**Core Principle**: A good fix addresses the root cause, not symptoms. Evaluate each PR for
long-term correctness, whether it fixes the right producer of the input shape, and whether each
review comment is actionable before acting.

**Principled review rule**: If the PR handles an assert, crash, ICE, malformed IR, or impossible
AST shape, question the input shape first. Is that AST/IR/witness/type shape valid and intentional?
If not, the right fix is usually in the upstream producer, not in a narrow consumer-side special
case.

**Usage**: `/slang-review-pr <pr-url-or-number> [--wsl]`

Where `<pr-url-or-number>` is:
- A PR URL (e.g., `https://github.com/shader-slang/slang/pull/10759`)
- A PR number (e.g., `10759`)

`--wsl` forces native WSL `git`/`gh` when running under WSL. Without it, WSL
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
PR="$ARGS"

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

## Principled Review Methodology

Treat the changed code as a representation-flow problem, not just a local diff. A crash in an IR
pass may be caused by ill-formed IR produced during `lower-to-ir`, but the root cause may be
farther upstream: type checking may have produced an invalid AST shape, a `DeclRef` with missing or
incorrect substitution arguments, the wrong lookup path, an incorrect witness form, or invalid
generic nesting. In some cases the bug may reveal a flaw in the language design rather than a local
implementation bug; flag that explicitly instead of endorsing a local workaround.

Ask these questions for every non-trivial helper, fallback, or special case in the PR:

1. Why is this new logic or helper needed? What exact problem is it solving?
2. Why is a new special handling path being added? Is the input pattern valid, or should an upstream
   producer be fixed so this pattern is never produced?
3. If the PR mirrors a pre-existing workaround, is this the right moment to refactor and unify those
   workarounds around a more principled representation?
4. Which test fails without the change, and does that failure prove this layer owns the fix?
5. What existing mechanism should already handle this case, such as `substitute`, `resolve`,
   canonical builders, witness lookup, or generic specialization?
6. Is any code structurally walking operands, substitutions, lookup paths, witness chains, IR users,
   or AST parents just to rule out a one-off special case? If so, ask why this is not a missing rule
   in canonicalization, substitution, lookup, witness formation, or another established producer.
7. Does a new utility duplicate an existing utility? Search nearby helpers and shared utility
   headers before accepting a new abstraction.
8. Is the utility name honest about the behavior? Flag names that are too broad, too narrow, or tied
   to the motivating case rather than the actual semantics. For example, if a helper named
   `isDifferentiableFunc...` checks a property that is not specific to differentiability, ask for a
   more general name.

Flag predicate-ladder fixes like `if (A && B && C && D) then do this special thing` unless the PR
proves that the input shape is valid and this layer owns the behavior. Prefer comments and PR
descriptions that explain the whole user-code scenario conversationally: "Consider this example:",
the relevant source snippet, and a step-by-step explanation of what the compiler builds and why the
fix preserves the invariant.

Also flag any new or changed code comment that a reader might not understand without hidden context.
A good comment includes enough user code, producer-to-consumer flow, and local invariant for a
reviewer to understand why the code exists without reconstructing the entire investigation.
If an explanation uses abstract, hand-wavy terms, or invents terminology that is not defined or used
elsewhere in the codebase, request clearer wording grounded in existing Slang terms and the concrete
example.

---

## Phase 1: GATHER CONTEXT

Collect all information about the PR, its linked issues, and review feedback in parallel.

### Step 1: Fetch PR Details

```bash
# PR metadata, body, and reviews
"$GH" pr view <number> --repo shader-slang/slang \
  --json title,body,state,headRefName,baseRefName,url,isCrossRepository,headRepository,headRepositoryOwner

# Review comments (inline code comments)
"$GH" api repos/shader-slang/slang/pulls/<number>/comments

# Reviews (top-level review bodies)
"$GH" api repos/shader-slang/slang/pulls/<number>/reviews
```

### Step 2: Fetch Linked Issues

Extract closing issue references from the PR body. Accept both full references
such as `Fixes shader-slang/slang#10153` and bare references such as
`Fixes #10153`. Resolve bare references to `shader-slang/slang`, preserve the
repository from full references, and deduplicate by `owner/repo#number` before
fetching issues. For each deduplicated reference, parse the `owner/repo` and
`number` components from the same reference, then fetch that issue:

```bash
"$GH" issue view <number> --repo <owner/repo> --json title,body,labels
```

### Step 3: Fetch Review Thread Status

Paginate to avoid missing unresolved threads on larger PRs:

```bash
# Fetch all review threads (paginate if hasNextPage is true)
"$GH" api graphql -f query='
{
  repository(owner: "shader-slang", name: "slang") {
    pullRequest(number: N) {
      reviewThreads(first: 100) {
        pageInfo { hasNextPage endCursor }
        nodes {
          id
          isResolved
          comments(first: 100) {
            nodes {
              databaseId
              author { login }
              body
            }
          }
        }
      }
    }
  }
}'
```

If `hasNextPage` is true, re-query with `after: "<endCursor>"` until all threads are fetched.

### Step 4: Sync the Branch

```bash
# Preferred: works for same-repo and fork-based PRs
"$GH" pr checkout <number>

# Manual fallback if you need explicit control:
# Same-repo PR
"$GIT" fetch origin <headRefName>
"$GIT" checkout -B <headRefName> --track origin/<headRefName>

# Fork-based PR
"$GIT" remote get-url pr-author >/dev/null 2>&1 || \
  "$GIT" remote add pr-author https://github.com/<headRepositoryOwner.login>/<headRepository.name>.git
"$GIT" fetch pr-author <headRefName>
"$GIT" checkout -B <headRefName> --track pr-author/<headRefName>
```

If you add the fork remote manually, add it only once. Reuse the existing remote
on later review iterations.

---

## Phase 2: REVIEW THE APPROACH

**This is YOUR independent assessment of the code.** Phase 3 (next) is your response
to EACH reviewer comment. These are distinct — a reviewer may raise something you
missed, or you may disagree with a reviewer. Do not skip Phase 3 even if you feel
you covered the comments during Phase 2.

Read the actual code changes and evaluate the solution against the linked issue.
Record issues found here as Phase 2 findings before moving on to review-thread triage. In
particular, structural walking, duplicated utilities, misleading helper names, opaque comments, and
invented terminology are approach-review concerns: flag them while assessing whether the PR's
solution is principled, not as a generic cleanup checklist at the end.

### Step 1: Read the Changed Files

Read every file touched by the PR. Do not evaluate code you haven't read.

Focus on:
- **Source changes** (`source/slang/`): The core fix
- **Diagnostic definitions** (`slang-diagnostics.lua`): New error codes, message clarity
- **Tests** (`tests/`): Coverage of the fix, edge cases, negative tests

### Step 2: Evaluate Root Cause Fix

Answer these questions:

1. **Does this fix the root cause?** Or does it mask a symptom?
   - A root cause fix prevents the problem from occurring
   - A symptom fix catches the problem after it occurs (e.g., adding a null check
     without asking why the null happened)
   - For asserts, crashes, malformed IR, or impossible AST shapes, verify whether the input shape
     itself is valid. If not, the fix should usually be in the producer of that shape.

2. **Is it optimal?** Could the same result be achieved with less code, fewer edge cases,
   or in a more maintainable way?

3. **Is it focused?** Does the PR do only what's needed, or does it include unrelated
   refactoring, unnecessary abstractions, or speculative features?

4. **Is it correct long-term?** Will this hold up as the codebase evolves, or does it
   rely on fragile assumptions?

5. **Are there missing cases?** Does the fix handle all variants of the problem, or only
   the specific reproducer from the issue?

6. **Is the representation principled?** Does the PR rely on a predicate ladder or one-off helper
   to recognize a malformed pattern, or does it make the frontend, AST builder, witness synthesis,
   `lower-to-ir`, or IR producer create the correct canonical representation?

7. **Does this need design input?** If the PR cannot define what the canonical AST/IR/witness shape
   should be, flag it as a language-design or representation-design question before accepting a
   local fix.

8. **Is structural walking justified?** Flag code that recursively walks operands, substitution
   chains, lookup paths, witness chains, IR users, or AST parents to detect a special case. Ask why
   the established canonicalization, substitution, lookup, witness, or lowering rule does not
   produce the right shape before this code runs.

9. **Are helpers duplicated or misnamed?** For every new utility, check whether an existing helper
   already does the job. Also check whether the name matches the actual behavior: too-general names
   hide constraints, and too-specific names such as `isDifferentiableFunc...` are misleading if the
   body is not differentiability-specific.

### Step 3: Evaluate the Diagnostic Messages (if applicable)

For diagnostic-related PRs:
- Is the error message accurate for all cases where it fires?
- Could reusing an existing diagnostic code be misleading in the new context?
- Does the message give actionable guidance to the user?

### Step 4: Evaluate Test Coverage

Check that tests cover:
- The positive case (the bug is fixed / the diagnostic fires)
- Negative cases (the fix doesn't break valid code / the diagnostic doesn't fire incorrectly)
- Edge cases (related patterns, different targets, generic/parametric types)
- The original reproducer from the linked issue
- **All applicable backends**: Tests should have `//TEST` lines for all relevant
  targets, not just one. Target-independent features need at minimum `-cpu` and
  `-spirv`. Flag tests that only test a single backend when the fix applies broadly.

### Step 5: Evaluate Comments and Explanations

Flag every new or changed code comment, helper comment, and PR-description explanation that a reader
might not have enough context to understand. Comments should not rely on shorthand labels such as
"AST trace" or "IR trace" without explanation. Prefer conversational explanations:

1. Start with "Consider this example:" and include the relevant user code.
2. Explain what the compiler builds step by step, naming the producer functions or passes.
3. State the invariant being preserved and which downstream consumer relies on it.
4. Explain why the fix belongs at this layer rather than in an upstream producer or downstream
   consumer.

Also flag:

- Large bodies of new logic with no explanation of the invariant or control-flow intent.
- Explanations that are not self-contained, so the reader needs hidden context from the debugging
  session to understand them.
- Comments that talk in abstract or hand-wavy terms instead of grounding the explanation in user
  code and named compiler concepts.
- Invented terminology that is not defined locally and is not used elsewhere in the codebase.

---

## Phase 3: EVALUATE REVIEW FEEDBACK

**CHECKPOINT**: Before proceeding, list every unresolved review thread by ID/file.
Each one MUST appear in the classification table below. If there are zero threads
to evaluate, state that explicitly. Do not skip this phase — even if you feel you
already covered the comments during Phase 2, the structured evaluation ensures
nothing is missed and gives the user a clear action list.

### Step 1: Enumerate all threads

List every unresolved thread: `#{number} — {file}:{line} — {one-line summary}`

### Step 2: Classify each thread

| Category | Criteria | Action |
|----------|----------|--------|
| **Valid + Actionable** | Points to a real bug, missing case, or incorrect behavior | Implement the fix |
| **Valid + Out of Scope** | Correct observation but unrelated to this PR's purpose | Reply acknowledging, don't fix |
| **Valid + Nice-to-Have** | Improves quality but not critical | Implement if easy, otherwise acknowledge |
| **Needs Context** | Comment or PR explanation is technically useful but lacks enough source/context for readers | Expand the explanation |
| **Unprincipled Helper** | New utility duplicates existing logic, has a misleading name, or structurally walks to patch one shape | Reuse, rename, or move the fix to the producer |
| **Incorrect** | Based on wrong assumptions about the code | Reply explaining why |
| **Trivial Nitpick** | Style, wording, minor formatting | Apply if trivial, otherwise acknowledge |

### Priority Order

Address feedback in this order:
1. **Bugs / correctness issues** (e.g., missing ErrorType guard, cascading diagnostics)
2. **Unprincipled representation fixes** (e.g., consumer-side predicate ladders over malformed input)
3. **Structural walking / helper issues** (e.g., duplicate utilities, misleading names, ad hoc graph walks)
4. **Missing test coverage** (e.g., negative tests, edge cases)
5. **Diagnostic message accuracy** (e.g., misleading error text)
6. **Code clarity and context** (e.g., comments, variable names, insufficient full-context examples)
7. **Out-of-scope suggestions** (reply only)

### Step 3: Present findings to user

**STOP and present** the full classification table and your recommended actions.
Ask: "Which items should I implement? All actionable, specific items (list numbers), or none?"

The user may also provide additional context or disagree with classifications.

---

## Phase 4: IMPLEMENT FIXES

Only implement items the user approved in Phase 3.

### Step 1: Build if Needed

If you switched from another branch, the binary may be stale. See the `slang-build` skill for
platform-aware build instructions and preset selection.

### Step 2: Make Changes

- Fix one concern per commit when possible
- Follow existing code patterns in the file
- Add comments only for non-obvious logic
- For new diagnostics: choose a code number adjacent to related diagnostics
- When adding or revising explanatory comments, use full-context conversational examples. Include
  the relevant user code, explain the producer-to-consumer flow step by step, and state why the fix
  belongs at this layer.
- Do not implement a narrow `if (A && B && C && D)` workaround just because it satisfies a review
  thread. First confirm the input pattern is valid; otherwise fix the upstream producer or explain
  why the issue needs design discussion.
- Before adding a new utility, search for an existing helper that already expresses the invariant.
  If you keep the new helper, name it for its actual behavior, not for the first motivating case.
- If a fix requires structural walking, first try to replace it with a producer-side canonical form
  or an existing canonicalization/substitution rule. Keep the walk only when the walked shape is
  valid input and the comment explains why.

### Step 3: Test

Use the `slang-run-tests` binary selection rule for `$SLANG_TEST` and
`$SLANGC`. Under WSL with a Windows-hosted build, that means
`slang-test.exe`/`slangc.exe`, and the agent must stop if those binaries are
missing.

```bash
# Run the specific test(s) affected by changes
"$SLANG_TEST" tests/path/to/test.slang

# If modifying compiler source, also run related tests
"$SLANG_TEST" tests/path/to/related-tests/
```

### Step 4: Format

```bash
./extras/formatting.sh
```

### Step 5: Commit and Push

One commit per logical fix. Follow commit rules from the `slang-create-issue` skill.
Commit message should reference the review feedback:

```bash
"$GIT" add <files>
"$GIT" commit -m "$(cat <<'EOF'
Address review: <short description of what was fixed>

<1-2 lines explaining what changed and why>
EOF
)"

# If the branch already tracks the PR head remote, plain `$GIT push` is enough
"$GIT" push

# If the branch has no upstream yet, set it explicitly
"$GIT" push -u <head-remote> HEAD:<headRefName>
```

If push is rejected (remote has new commits), rebase first:

```bash
"$GIT" pull --rebase
"$GIT" push
```

---

## Phase 5: SUGGEST REPLIES

**Do NOT post replies automatically.** Present draft replies for user approval.

### Step 1: Draft replies for each thread

For each thread from Phase 3, prepare a suggested reply. Use these formats:

- **Implemented**: "[Agent] Applied. <brief description of what changed>. See <commit-hash>."
- **Out of scope**: "[Agent] Acknowledged. Out of scope for this PR. Will address separately."
- **Won't fix**: "[Agent] This is intentional because <reason>."
- **Question answered**: "[Agent] <concise answer>"

### Step 2: Present to user

Show all draft replies in a table:

| Thread | File | Draft Reply | Post? |
|--------|------|-------------|-------|
| #1 | slang-ir-foo.cpp:123 | [Agent] Applied. Added null check... | ? |
| #2 | slang-ir-foo.cpp:456 | [Agent] Out of scope for this PR... | ? |

**STOP and ask**: "Which replies should I post? All, some (list numbers), or none?"

### Step 3: Post approved replies

Only post the replies the user approved:

```bash
"$GH" api repos/shader-slang/slang/pulls/<number>/comments/<comment-id>/replies \
  -f body="<approved-reply>"
```

### Step 4: Resolve threads (only for posted replies)

Only resolve threads where a reply was posted and the concern was addressed:

```graphql
mutation {
  resolveReviewThread(input: {threadId: "<thread-id>"}) {
    thread { isResolved }
  }
}
```

Do NOT resolve threads when:
- The user chose not to reply
- The reviewer explicitly asked for follow-up discussion
- You're unsure whether the response addresses the concern

---

## Phase 6: REPORT

Present a concise summary to the user:

### When Reviewing a New PR

```
## PR #N Review

**Root cause fix?** Yes/No — [1 sentence explanation]
**Optimal?** Yes/No — [1 sentence]
**Long-term correct?** Yes/No — [1 sentence]
**Input shape principled?** Yes/No — [is the handled AST/IR/witness/type shape valid, or should a producer change?]
**Explanation context sufficient?** Yes/No — [whether comments/PR text include enough user-code context and step-by-step flow]

## Review Feedback

| Thread | Feedback | Valid? | Action |
|--------|----------|--------|--------|
| ... | ... | ... | ... |

All N threads resolved / M remain.
```

### When Addressing Feedback

```
## Changes Made (commit <hash>)

| Thread | Action |
|--------|--------|
| ... | ... |

All N threads resolved.
```

---

## Phase 7: POST SUMMARY (optional)

After all other phases are complete, offer to post a brief summary to the PR.
This is a high-level overview — do NOT repeat thread-level detail already covered
by individual replies.

**STOP and ask the user** before posting. Show a preview.

Format:

```
## [Agent] Review Summary

**Assessment**: [1-2 sentences — is the root cause fix correct, any concerns]

**Actions taken**: [what was implemented, commit references if applicable]

**Open items**: [anything remaining — unresolved questions, follow-up needed]
```

---

## Iteration

The user may ask to check for new comments after pushing fixes. Repeat from Phase 1
Step 3 (fetch thread status) — only process unresolved threads.

When iterating:
- Always rebuild if the branch was used by another PR in between
- Only read files that are relevant to the new comments
- Don't re-reply to already-resolved threads

---

## Anti-Patterns

1. **Blindly applying all suggestions**: Evaluate each comment. Bot reviewers sometimes
   suggest changes that are incorrect, out of scope, or unnecessary.

2. **Resolving without replying**: Always reply before resolving. The reply is the record
   of what was done.

3. **Large omnibus commits**: One commit per logical fix makes review easier.

4. **Not rebuilding after branch switch**: The binary in `build/RelWithDebInfo/bin/` corresponds
   to whatever branch was last built. Always rebuild after switching branches.

5. **Ignoring exhaustive test mode**: `DIAGNOSTIC_TEST:SIMPLE` with exhaustive mode catches
   unexpected diagnostics. If adding a negative test case, annotate ALL diagnostics it
   produces, not just the one you're interested in.

6. **Pushing without testing**: Always run the affected tests before pushing. A broken push
   triggers CI and wastes reviewer time.
