# Experts: Tess and Yong in the review bank

Source: `tasks/review/*/task.toml`, key `[metadata].threads_json`, in the private eval bank (315 tasks, 882 human threads). Each thread is a root inline review comment by a human maintainer, with `id`, `author`, `path`, `line`, `body`, `nit`, `outdated`, `created_at`. The same list is inlined into `tests/test.sh` as the verifier's expected data. Replies, bot comments, PR-author comments, and top-level PR comments are not stored. Every stored thread has a file and line, so "inline vs top-level" is 100% inline for both authors.

| Author | GitHub | Threads | Share of 882 | Tasks | PRs | Nits | Median words |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Tess (Theresa Foley) | `tangent-vector` | 231 | 26.2% | 33 | 30 | 2 | 58 |
| Yong (Yong He) | `csyonghe` | 13 | 1.5% | 9 | 9 | 0 | 23 |

Tess reviewed 15 PRs by `nv-slang-bot[bot]` (110 threads) and 15 PRs by nine human authors (121 threads). Yong's sample is small; his rules below are stated with that caveat.

Quotes are trimmed to 25 words or fewer; `[n]` is the thread index in `tess.txt` or `yong.txt` next to this file.

## (a) Terminology

### Tess: terms she uses

Counts are mentions / threads across her 231 threads (regex over bodies, code blocks included).

| Term | Mentions / threads | How she uses it |
| --- | ---: | --- |
| layout, layout unit, `LayoutResourceKind` | 46/17, 22/5, 7/4 | Size and alignment measured in a unit; "unit" and "kind" are the same notion. |
| operation, subroutine, routine, procedure, helper | 37/24, 32/21, 22/18, 8/7, 22/19 | Her words for a function; "helper" is often pejorative. |
| `this` parameter, parameter-passing mode, effective | 34/11, 14/10, 23/8 | The mode (`in`, `inout`, `ref`, borrow) a parameter is passed with, after context is applied. |
| diagnose / diagnostic | 33/17 | Reporting an error or warning; "always diagnose on an unknown modifier". |
| pass | 29/18 | An IR pass; she wants a verb in its name. |
| documentation comment, implementation comment, implementer-facing, client | 29/20, 13/10, 10/7, 19/15 | Two comment audiences: the client of an abstraction and its future maintainer. |
| policy, rationale, contract | 27/17, 18/14, 18/12 | A design decision, its justification, and the behavioral contract of an API. |
| predicate, proposition | 22/14, 1/1 | A Boolean-returning function; a Boolean field is named as a proposition. |
| invariant, precondition, assert | 14/6, 7/6, 19/14 | What must hold; violations are asserted, never handled. |
| early-out | 15/10 | A `return`/`continue`/`break` before the primary path. |
| bytes, byte-granularity, uniform | 15/11, 6/4, 8/7 | "uniform" is a legacy name for bytes; new code says bytes. |
| decl-ref | 11/4 | A reference to a declaration with substitutions. |
| disposition, verdict | 16/6 | The result of a validity check. |
| AST-to-IR lowering, IR lowering, front-end | 5/3, 7/5 | The lower-to-IR step; the front end owns semantic decisions. |
| code smell, band-aid, WAR, CYA, dirty laundry, bottleneck | 9/9, 2/2, 4/4, 4/4, 2/2, 5/4 | Review vocabulary: a workaround, a cowardly guard, history in a comment, one shared routine. |
| standard module(s) | 6/3 | The separately shipped modules; "monolithic" vs "separate" library. |
| entry-point uniform parameter ("launch parameter") | 1/1, 1/1 | She writes the long form and quotes the short one. |
| borrow, `borrow in`, const ref | 3/2, 3/1 | The correct concept is an immutable borrow; "const ref" is a mistake. |
| cumulative offset, absolute offset | 4/2, 4/1 | All offsets are relative to something; "absolute" is wrong. |
| opaque handle, descriptor heap, derivative group, `Never` | 7/5, 3/3, 2/2, 1/1 | Feature nouns from the PRs she reviewed. |

### Tess: corrections of words

| # | Correction | Quote (≤ 25 words) | Task | PR |
| --- | --- | --- | --- | --- |
| C1 | "uniform" → bytes, byte-granularity | "what is actually being discussed here is *bytes* and *byte-granularity* usage information." [3] | slang-pr-11135-d240653 | 11135 |
| C1 | same | "we should avoid ever using the word "uniform" to mean bytes." [42] | slang-pr-12306-75e037d | 12306 |
| C1 | file name | "I would advocate for `slang-ir-byte-granularity-usage.*`." [3] | slang-pr-11135-d240653 | 11135 |
| C2 | "exception" → error; "throw" → raise | "we should be careful not to refer to Slang's error handling mechanism in terms of exceptions, and instead refer to them as "errors."" [27] | slang-pr-12209-695f596 | 12209 |
| C2 | same | "I would also mildly prefer that we describe it as "raising" an error rather than throwing" [32] | slang-pr-12209-695f596 | 12209 |
| C3 | "absolute offset" → cumulative offset | "we should *not* use the term "absolute" ... The term "cumulative" is carefully and intentionally chosen." [105] | slang-pr-12715-6f2f414 | 12715 |
| C3 | "reflection offset" → offset | "The term "reflection offset" is meaningless. Just use "offsets" here." [105] | slang-pr-12715-6f2f414 | 12715 |
| C4 | "const ref", `ConstRef` → (immutable) borrow | "the whole "const ref" terminology is inaccurate and never should have been introduced ... The correct concept is an (immutable) borrow." [166] | slang-pr-13401-c99f962 | 13401 |
| C4 | pass name | "give it a more accurate name like `transformByValueParamsToBorrows`" [168] | slang-pr-13401-c99f962 | 13401 |
| C5 | `const` (ref access) → `readonly` | "The `const` keyword in a context like this is being accepted as a legacy alias for `readonly`. The name `const` is incorrect" [182] | slang-pr-13406-66523f1 | 13406 |
| C5 | printing | "This should be `ref readonly` or `readonly ref`." [180] | slang-pr-13406-66523f1 | 13406 |
| C6 | "array selection" → index, get element, subscript | "Array "selection" is not a term we use in the Slang compiler codebase ... We index into an array. We get elements from it." [206] | slang-pr-13539-7228ad1 | 13539 |
| C7 | "target" (of a modifier) → subject | "refer to the construct being modified as the *subject* rather than the *target*" [90] | slang-pr-12596-5553973 | 12596 |
| C8 | "record" → collect | "I'm honestly not sure why the term "record" is being used here instead of "collect", since the overall pass uses "collect" as the terminology." [8] | slang-pr-11135-d240653 | 11135 |
| C9 | "check" (noun, result) → disposition, verdict | "Referring to this type as a "check" seems semantically incorrect. It is more accurately the disposition or verdict" [87] | slang-pr-12596-1dbdab4 | 12596 |
| C10 | "kind" ↔ "unit" (layout) | "seems to be mixing up the notions of "unit" and "kind," even though they mean the same thing here." [61] | slang-pr-12544-479e4da | 12544 |
| C10 | parameter category | "The `Uniform` "parameter category" is used to represent everything that is measured in bytes" [0] | slang-pr-11135-d240653 | 11135 |
| C11 | `get` → `calc`/`compute` for non-trivial accessors | "an accessor-like function that involves "non-trivial" computation should use `calc` or `compute` or similar for its verb, and not `get`." [114] | slang-pr-12715-6f2f414 | 12715 |
| C12 | `isRefParamPassingMode` → `isByReferenceParamPassingMode` | "The name `isRefParamPassingMode` implies that it checks for exactly the single `ParamPassingMode::Ref`" [183] | slang-pr-13406-66523f1 | 13406 |
| C13 | `defer` tied to a scope → to an enclosing statement | "refers to deferred statements as being associated with a *scope* rather than with an enclosing *statement*." [30] | slang-pr-12209-695f596 | 12209 |
| C13 | static vs runtime scope | "doesn't distinguish between static/lexical scopes ... from dynamic/runtime scopes (individual "instances" of the static scopes" [30] | slang-pr-12209-695f596 | 12209 |
| C14 | "on the fragment stage" → "in" | "I think these uses of "on" should be "in." E.g., "A `discard` is only allowed *in* the fragment stage."" [36] | slang-pr-12209-695f596 | 12209 |
| C15 | "operator" means an actual operator | "**actual operators**: the things that may appear as the operator in an OperatorExpr. Prefix, postfix, and infix opereators." [130] | slang-pr-12781-b01c9b9 | 12781 |
| C16 | pass names carry a verb | "it isn't clear from the name whether the pass will *inject* undefined opaque handles, *eliminate* them, *diagnose* them, etc." [217] | slang-pr-14081-41c22bd | 14081 |
| C17 | "monolithic" vs "separate"; "compiler-embedded" | ""monolithic" vs "separate" as terms for whether we generate a single bundled representation of the standard modules, or separate representations" [212] | slang-pr-14001-6697536 | 14001 |
| C18 | Boolean field named as a proposition | "give it a name that works as a proposition (or a predicate, but that doesn't apply in this case)." [165] | slang-pr-13401-c99f962 | 13401 |
| C19 | doc comment vs implementation comment | "doc comments are for clients, and implementer-facing comments are used to document the pertinent information that cannot be gleaned just by reading the code." [106] | slang-pr-12715-6f2f414 | 12715 |
| C19 | `//` counts too | "whether it is written with `///` or `//`, it is a documentation comment" [102] | slang-pr-12701-1cb3b76 | 12701 |
| C20 | "getX" when the mode is inferred → "getEffectiveX" | "to be clear about the fact that it queries the final (effective) parameter-passing mode for a `this` parameter" [144] | slang-pr-13213-84be79e | 13213 |
| C21 | "tiny" in comments | "The recurring use of "tiny" in comments ... comes across more as advertisement rather than a technically-precise explanation" [57] | slang-pr-12421-8cd02a1 | 12421 |
| C22 | "authored" in a comment | "What in the world is the word "authored" doing here? Of *course* it's authored. All the code is authored." [85] | slang-pr-12596-1dbdab4 | 12596 |
| C23 | binding semantics live in entry-point layout, not struct fields | "The canonical representation of information about varying parameters (including their semantics) should be the layout information attached to the entry point itself" [139] | slang-pr-12885-ba7e76e | 12885 |
| C24 | by-pointer policy is a pointer type, not an address space | "cases where we want to influence how parameters get declared in emitted source are modeled as distinct IR pointer type opcodes, not address spaces." [178] | slang-pr-13401-c99f962 | 13401 |

### Yong: terms he uses

Thirteen threads, 334 words; counts are mentions / threads.

| Term | Mentions / threads | How he uses it |
| --- | ---: | --- |
| language version, `#language slang 2025`, Slang 2026 | 4/3 | A test pins its version; syntax meaning changes by version. |
| capability, CapabilitySet, join, profile | 4/2, 2/1, 1/1, 1/1 | Join the user's atoms into one set, then compare against the profile. |
| invariant, assert, internal error | 2/2, 2/2, 1/1 | A broken invariant is a loud failure. |
| lowered, legalization | 2/2, 1/1 | Helper types are lowered during legalization and never reach emit. |
| emit | 2/1 | The output stage; it must not see unlowered types. |
| inner operand, cast | 1/1, 1/1 | A round-trip cast returns its inner operand. |
| chase the uses | 1/1 | Following def-use chains; suspect without a failing test. |
| tuple construction, deprecate | 1/1, 1/1 | Language-reference vocabulary. |
| `Dictionary<K*, V*>` | 1/1 | Declare maps with their exact pointer types. |

Yong makes no explicit word corrections in this sample; his terminology evidence is usage only.

### Candidate glossary changes

Status is checked against `../slang-compiler/GLOSSARY.md` and `../slang-language/GLOSSARY.md`: new = no entry; agrees = entry exists and matches; conflicts = entry exists and differs.

| Term | Canonical | Avoid | Context | Author | Evidence (threads) | Status |
| --- | --- | --- | --- | --- | ---: | --- |
| Bytes (layout unit) | bytes; byte-granularity usage | uniform (meaning bytes); uniform usage; uniform field usage | compiler | Tess | 9 | new |
| Parameter-passing mode | parameter-passing mode | parameter direction (compiler prose); passing convention | compiler | Tess | 10 | conflicts: language draft names the concept "Parameter direction" |
| Documentation comment / implementation comment | documentation comment (client contract); implementation comment (maintainer strategy) | mixing the two audiences; "dirty laundry" | conventions | Tess | 24 | new |
| Early-out | early-out | bail-out; guard (for the statement itself) | conventions | Tess | 10 | new |
| Effective `this` parameter | effective `this` parameter; effectively static | declared mode (when the computed one is meant) | compiler | Tess | 6 | new |
| Layout unit | layout unit (`LayoutResourceKind`) | kind (bare); parameter category | compiler | Tess | 5 | agrees; adds "kind" to Avoid |
| Disposition | disposition (result of a validity check) | check (as a noun for the result); verdict is acceptable | compiler | Tess | 5 | new |
| Internal error | internal error (an out-of-contract IR shape reaching a later phase) | fallback; defensive handling; silent continue | compiler | both | 4 | new |
| Decl-ref | decl-ref | DeclRef (prose); declaration reference | compiler | Tess | 4 | agrees |
| Error (Slang error handling) | error; raise an error | exception; throw an exception (prose) | language | Tess | 3 | new |
| Borrow-in parameter | borrow-in parameter; immutable borrow | const ref; ConstRef; constref | compiler | Tess | 3 | agrees |
| Readonly ref access | readonly (ref access qualifier); `readonly ref` | const (as the access qualifier) | language | Tess | 3 | new; extends GLOSSARY-MAP #11 |
| Lower-to-IR | lower-to-IR; AST-to-IR lowering | IR gen; IR generation; codegen | compiler | Tess | 3 | agrees; add "AST-to-IR lowering" as accepted long form |
| Standard module library | monolithic vs separate standard-modules library; compiler-embedded | embedded (bare) | compiler | Tess | 3 | agrees; extends "Standard module" |
| Operator (actual) | operator (prefix, postfix, infix in an operator expression) | treating `operator=`-style names as operators | language | Tess | 3 | new |
| Language version | language version; pinned with `#language slang <year>` | module version; dialect (for the version) | language | both | 6 | new |
| Cumulative offset | cumulative offset | absolute offset; reflection offset | compiler (reflection API) | Tess | 2 | new |
| Calc/compute accessor | `calc`/`compute` prefix for non-trivial accessors | `get` for expensive computation | conventions | Tess | 2 | new |
| Entry-point uniform parameter | entry-point uniform parameter | launch parameter | language | Tess | 2 | agrees |
| Legalization | legalization (passes lowering target-illegal types/ops before emit) | — | compiler | both | 2 | agrees; generalizes "Type legalization" |
| Capability set join | join (of capability sets) | merge; union (when join is meant) | compiler | both | 2 | agrees; extends "Capability set" |
| Index into an array | index into; get an element; subscript | select from an array; array selection | compiler | Tess | 1 | new |
| Subject (of a modifier) | subject | target (ambiguous with compilation target) | compiler | Tess | 1 | new |
| Collect | collect (gathering in a pass) | record (as the verb) | conventions | Tess | 1 | new |
| Binding semantic | binding semantic; entry-point layout is the canonical source | semantic (bare) | language | Tess | 1 | conflicts (soft): compiler prose uses bare "semantics" |
| WAR | workaround (WAR) | — | review vocabulary | Tess | 4 | new |
| Tuple construction | tuple construction `(a, b)` (Slang 2026+) | — | language | Yong | 1 | new |

## (b) Tess's rules

Each rule is general; PR-specific names appear only in quotes.

### R1. Every early-out is an assertion or carries a justification

Rule: a `return`, `continue`, or `break` before the primary path either asserts a precondition or explains why the case arises and is handled correctly.
Example: `if (!layout) continue;` in a loop over parameters becomes `SLANG_ASSERT(layout)` or gets a comment naming the producer that leaves it null.
- "The above rules should apply to every single early-out from a function/loop/etc. that appears in any PR for the Slang codebase." [18] slang-pr-11225-037521c
- "every single early-out `return`/`continue`/`break`/etc. should include a comment that fully justifies its existence." [50] slang-pr-12421-8cd02a1
- "This early-out CYA code is a hallmark of agent's trying to write "safe" code and instead just leaving latent bugs" [172] slang-pr-13401-c99f962

### R2. Assert invariants; never default silently

Rule: when the design says a shape cannot occur, assert it; do not return zero, null, or false for it.
Example: a byte-size query on an unbounded type asserts or reports, rather than returning 0.
- "the right thing to do would be to assert-fail here ... rather than silently glossing over the issue" [1] slang-pr-11135-d240653
- "ensure that invariants (including preconditions, postconditions, etc.) that the design/architecture says are assumed are then *asserted* in the implementation" [108] slang-pr-12715-6f2f414
- ""what should the byte size be for a type with an *unbounded* size in bytes? I know! Zero!!!"" [5] slang-pr-11135-d240653

### R3. Documentation comments state the client contract; implementation comments explain strategy

Rule: a comment on a declaration says what it does and promises, for its caller; strategy and caveats go inside the body.
Example: `/// Returns the stride, in bytes, between consecutive elements.` on the declaration; the two-phase walk is explained inside.
- "A documentation comment should state the behavioral contract of a subroutine/type/whatever in terms that the client of the abstraction cares about." [56] slang-pr-12421-8cd02a1
- "doc comments are for clients, and implementer-facing comments are used to document the pertinent information that cannot be gleaned just by reading the code." [106] slang-pr-12715-6f2f414
- "the comment here fails to do the most basic thing: tell the reader what the procedure *does*." [102] slang-pr-12701-1cb3b76

### R4. No process or history in code

Rule: comments never cite issues, PRs, or the task at hand, and never record what a routine is not or used to be.
Example: write "We skip hoistable instructions because the module owns them", not "Fixes #1234, see PR #1200".
- "Imagine your reader is receiving a zip file of the repository contents, and has no access to the github project with its issues/projects/etc." [78] slang-pr-12596-1dbdab4
- "Leave process-related and historical perspectives to the source control system, issue tracker, etc." [167] slang-pr-13401-c99f962
- "This part of the comment is what I'd call "dirty laundry."" [175] slang-pr-13401-c99f962

### R5. Comment voice: declarative, authorial "we", full sentences, written for a new contributor

Rule: comments describe the design in the present tense with "we", in grammatical sentences; no imperatives, fragments, or unexplained assumptions.
Example: "We cache the declared mode here because later phases cannot see the modifier", not "Cache the mode. Must run after signature checking."
- "Using imperative voice ("cache the desired `this`-passing mode...") instead of the project-preferred declarative voice with authorial "we"" [148] slang-pr-13213-84be79e
- "Please write implementer-facing comments in the style and tone of somebody explaining the program to a new contributor/maintainer joining the project." [121] slang-pr-12721-869097c
- "is near-meaningless LLM slop. I defy anybody to figure out what in the world the author is trying to convey" [150] slang-pr-13213-84be79e

### R6. Every pass, file, and non-trivial routine opens with problem, strategy, and rationale

Rule: the header states the problem solved, the solution strategy, the invariants relied on, and the alternatives rejected.
Example: a new IR pass file starts with a block comment naming the shapes it rewrites and why specialization beat inlining.
- "Where is the block comment at the top of this file explaining the purpose of the pass, the invariants it relies upon..." [7] slang-pr-11135-d240653
- "needs to start with a comment clearly stating: the problem to be solved, the solution strategy ... what alternatives were considered but dismissed" [54] slang-pr-12421-8cd02a1
- "This really needs a comment explaining the problem being solved, the solution strategy being employed here, and a rationale for why its the right approach." [100] slang-pr-12690-d26c284

### R7. Names say exactly what a thing does or is

Rule: prefer a long accurate name to a short vague one; conditional behavior appears in the name; a pass name carries its verb.
Example: a routine that stores a range only when non-empty is `collectRangeIfNonEmpty`, and a pass is `eliminateX`, not `x`.
- "A verbose-but-accurate name is always preferrable over a terse-but-meaningless/-confusing one." [3] slang-pr-11135-d240653
- "This should either be "maybe diagnose modifier validity" or "diagnose modifier validity, if needed"" [92] slang-pr-12596-5553973
- "Pick a verb and use it in the names..." [217] slang-pr-14081-41c22bd

### R8. Accessor verbs and Boolean names follow convention

Rule: `get` is for trivial access and `calc`/`compute` for real work; a Boolean field reads as a proposition and has a default value.
Example: `computeCumulativeOffset()` rather than `getCumulativeOffset()`; `bool shouldForwardAddresses = false;` rather than `bool forwardAddresses;`.
- "an accessor-like function that involves "non-trivial" computation should use `calc` or `compute` or similar for its verb, and not `get`." [114] slang-pr-12715-6f2f414
- "don't use a name that is an imperative verb phrase ... since that will make it look like the name of a procedure" [165] slang-pr-13401-c99f962
- "I would expect a single consistent name across all of them to hammer home the consistency." [119] slang-pr-12715-6f2f414

### R9. Compound conditions become named predicates; early-outs go one per statement

Rule: three or more `&&`/`||` become a named, documented predicate; two need a comment; each early-out case gets its own `if` and comment.
Example: `if (a && !b && c->isFoo())` becomes `if (shouldSkipParam(p))`, whose body handles each case with a comment.
- "Anything with 3 or more uses of `&&`/`||` is worth factoring out, realistically." [189] slang-pr-13487-53035c2
- "handle early-out cases like this one by one, rather than as a single complicated conditional." [216] slang-pr-14045-0c1668d
- "No condition with three `&&`s is ever a good idea." [134] slang-pr-12781-b01c9b9

### R10. Repeated logic bottlenecks through one named helper; prefer file-level statics to lambdas

Rule: a predicate or sequence written twice becomes one documented routine, and that routine is a `static` function rather than a local lambda.
Example: two call sites that each resolve link-time types inline share one `tryResolveAllLinkTimeTypesInDeclRef()`.
- "a single bottleneck routine that is clearly named to describe the policy that is needed in both of these cases" [25] slang-pr-12131-10f9418
- "If you find yourself writing the same predicate more than once, that's a strong indication that it should be factored out" [151] slang-pr-13213-84be79e
- "I have a personal preference for file-level `static`s because they make the contract of an operation explicit, force careful thought about naming" [21] slang-pr-11225-037521c

### R11. Return and store meaningful types

Rule: use an enum or `std::optional` instead of a Boolean or sentinel, and a named struct instead of a raw dictionary or out-parameter.
Example: a validity check returns `Disposition::{Allowed, Error, WarningOrError, NoVerdict}`, not `bool` plus an out-parameter.
- "if a function returns a Boolean I want it to be completely obvious at a call site what that result means" [93] slang-pr-12596-5553973
- "If we really need to represent an unset/invalid case here, then we should be using a `std::optional` or some other representation" [40] slang-pr-12306-75e037d
- "every two-state thing in the universe eventually gains more options and causes messes." [164] slang-pr-13371-431096f

### R12. Fix the producer; keep one canonical representation; consumers never patch

Rule: when a later phase meets a wrong shape, the phase that produced it is fixed. Policy is computed once in the front end and read as-is downstream.
Example: lowering that finds a declaration without its `this`-mode attribute reports a front-end bug instead of recomputing the mode.
- "It is never appropriate to hack in workarounds here." [154] slang-pr-13213-84be79e
- "The canonical representation of information about varying parameters (including their semantics) should be the layout information attached to the entry point itself" [139] slang-pr-12885-ba7e76e
- "slapping a band-aid on that resolves a single observed failure case, but doesn't systematically address the entire space of possibilities" [24] slang-pr-12131-10f9418

### R13. IR edits create new instructions; inlining is a last resort

Rule: replace an instruction by emitting a new one and moving its uses, never by retyping it. Propagate call-site facts by specializing a clone, not by inlining.
Example: a resource `select` becomes a new index `select` plus a new element fetch, and the old one is removed.
- "we should be *very* careful about going in and changing the types/operands/etc. of existing instructions, instead of creating *new* instructions to replace the old one." [205] slang-pr-13539-7228ad1
- "The *strong* explicit policy of the Slang project is that inlining is a last-resort solution." [222] slang-pr-14081-41c22bd
- "cases where we want to influence how parameters get declared in emitted source are modeled as distinct IR pointer type opcodes, not address spaces." [178] slang-pr-13401-c99f962

### R14. Flat code: early-outs first, `switch` over if-cascades

Rule: handle the exceptional cases first and leave the primary path unindented; enumerate cases with `switch`, not chained `if`s.
Example: `if (decl->findModifier<X>()) return;` at the top, then the main work with no nesting.
- "functions should always prefer flat code over nested and deal with early-out cases before the primary path." [147] slang-pr-13213-84be79e
- "Make this a proper `switch` over the cases, not just an `if`." [184] slang-pr-13406-66523f1
- "an `if` cascade (a code-smelly construct that should usually be avoided in favor of a `switch`, when possible)" [129] slang-pr-12781-b01c9b9

### R15. Stay in scope and respect recorded intent

Rule: change only what was asked; add no test that cements a design mistake; do not rewrite an expert's comment; introduce no undocumented policy.
Example: a PR asked to reject member operator declarations does not also rework the parser's operator table.
- "Nobody asked you to make changes to the parser here." [129] slang-pr-12781-b01c9b9
- "Do not add a test case covering a design mistake." [132] slang-pr-12781-b01c9b9
- "Be careful whenever overwriting comments, especially if I wrote them. I choose my words carefully and you should never assume you know better than me" [182] slang-pr-13406-66523f1

### R16. User guide shows the happy path; the reference holds every detail; neither cites the tracker

Rule: incomplete or discouraged features are described in the reference with a warning, not in the user guide, and docs never link to issues.
Example: a half-implemented modifier gets a reference note saying its use is discouraged and warnings may become errors.
- "the user guide should primarily focus on the "happy path" that we want users to be on." [143] slang-pr-13113-6d21984
- "I don't think it is appropriate for our user guide to be linking out to the issue tracker." [138] slang-pr-12820-81af8c1
- "indicating that these warnings may be turned into errors in a future Slang language version." [137] slang-pr-12820-81af8c1

### R17. Tests exercise the feature; self-review before posting; ask before writing a workaround

Rule: a test includes a conforming type and code that uses it; authors run the clarity review on themselves; blockers are raised, not patched.
Example: an interface test declares a type that conforms and a function that calls through the interface.
- "there are only the `interface` declarations and no comforming implementations nor code that works with the interfaces and conforming types" [101] slang-pr-12690-d26c284
- "Don't waste human time putting up PRs with diffs that a human like me will just be frustrated with." [84] slang-pr-12596-1dbdab4
- "ask for advice on how to resolve them, rather than jumping in to speculatively write gross WAR logic." [124] slang-pr-12721-869097c

### R18. Magic numbers become named constants; invariant-bearing state is private

Rule: a literal with meaning gets a name, and a type with an invariant hides its fields behind constructors and accessors.
Example: `static const int kMaxExpansionNotes = 3;` rather than a bare `3`; "exactly one pointer set" fields are private.
- "Please turn the magic number into a named constant." [46] slang-pr-12421-8cd02a1
- "If there are meaningful invariants that this type is supposed to uphold, then shouldn't the state be `private`" [107] slang-pr-12715-6f2f414

## (c) Yong's directives

Thirteen threads; each directive rests on one or two comments. "Same as" names the Tess rule above when the rule is shared.

### IR

**Y1. A helper type that exists only to be lowered must never reach emit.**
Plain English: the compiler replaces placeholder types with real ones before writing output. If one survives to output, that is a compiler bug and must fail loudly.
Ask: delete the emit-side handling of the placeholder type, lower it to `uint` in legalization, and make emit raise an internal error on sight.
- "We should have an invariant that the UntypeResourceHandleType never survive until emit. It shall be explicitly lowered to `uint` during the legalization steps" [0] slang-pr-11798-5f4a206
- "we should make it so that seeing an kIROp_UntypedResourceHandleType here is an internal error" [1] slang-pr-11798-5f4a206
Same as Tess R2 and R12.

**Y2. A round-trip cast simplifies to its inner operand; no search routine.**
Plain English: when a value is converted to another type and straight back, the simplifier uses the original value directly.
Ask: add the `uint2`/`uint64` to `DescriptorHandle` cast cases to the peephole pass, return the inner operand, and remove the round-trip-finding helper.
- "should add cases for uint2/64->DescriptorHandle casts here, and just return inner operand. Not sure why we needed the complex logic" [12] slang-pr-12263-31cc926
Same spirit as Tess [221] (fold simple rewrites into the general simplification passes).

**Y3. No use-chasing without a failing test.**
Plain English: code that follows every place a value is used must be justified by a test that fails without it.
Ask: name the test that breaks, or delete the loop.
- "Not sure why we need to chase the uses here. Which test will break without this?" [4] slang-pr-12080-3b0c212
Same as Tess R1 (justify or remove) and the CLAUDE.md rule "name the test that fails".

### Semantic checking

**Y4. Assert what an earlier stage already makes impossible.**
Plain English: if the parser guarantees a case cannot occur, the checker crashes loudly if it does, rather than handling it.
Ask: replace both handling branches in the statement checker with asserts.
- "Always prefer loud error over silent continuing when an invariant is broken." [10] slang-pr-12252-5915b22
- "same here, should assert." [11] slang-pr-12252-5915b22
Same as Tess R2.

**Y5. Mirror the sibling case; put the version-specific check first.**
Plain English: two parallel cases are written the same way, and the rule that depends on language version comes before the general one.
Ask: return the parent's visibility exactly as the interface case does, and move the interface case after the 2026-specific check.
- "should be fine to just `return getDeclVisibility(parentAggTypeDecl)` here to mirror the interface case above." [8] slang-pr-12151-f0371d1
Related to Tess R10 (one bottleneck) and [119] (parallel operations share one name).

**Y6. Combine inputs first, then compare once through a single utility.**
Plain English: fold all the user's capability flags into one set, then run one comparison against the profile.
Ask: join the `-capability` atoms into a `CapabilitySet` and call one utility that compares it with the profile's capabilities.
- "compute a join of all the specified `-capability` atoms first into a CapabilitySet, and then call into a single utility that compares" [5] slang-pr-12122-d2befaa
Same as Tess R10.

### Emit and core module

**Y7. Gate vendor opcodes on the user's capability and on the resource kind; define the combinations.**
Plain English: use the NVIDIA bindless conversion only when the user asked for it and the value is a texture or sampler. Say what happens when two extensions are both on.
Ask: delete the vendor-specific case; special-case texture, sampler, and combined kinds inside the default and EXT cases.
- "the conversion opcode is used only when spvBindlessTextureNV capability is specified by the user and only when we are dealing with Texture/Sampler resources" [9] slang-pr-12186-4fbe216
Yong only; adjacent to Tess R15 (no undocumented policy).

### Tests

**Y8. Pin the language version in a version-sensitive test.**
Plain English: a test about version-dependent behavior states its version, so a later default change cannot silently alter it.
Ask: add `#language slang 2025` as the first line.
- "should have an explicit `#language slang 2025` declaration here to pin the user module version in the test." [7] slang-pr-12151-f0371d1
Yong only.

### Style and types

**Y9. Declare containers with the exact types they hold.**
Plain English: a lookup table that always maps one kind of thing to another is declared with those types, so readers see its meaning.
Ask: declare the map as `Dictionary<IRDebugSource*, IRDebugCompilationUnit*>`.
- "so why isn't this type declared as `Dictionary<IRDebugSource*, IRDebugCompilationUnit*>` to better convey its meaning?" [6] slang-pr-12148-1cd2262
Same as Tess R11.

### Docs and language versions

**Y10. Document what a spelling means in each language version.**
Plain English: when syntax changes meaning in a newer version, the reference says so next to the old meaning.
Ask: note that `(,...,)` means tuple construction in Slang 2026 and later.
- "should also note that `(,...,)` in slang 2026 or later means tuple construction." [2] slang-pr-11953-dc27a6a
Related to Tess R16.

**Y11. Deprecate now what a future version will remove.**
Plain English: a feature slated for removal is marked deprecated in the docs today.
Ask: add a deprecation note to the conversions reference.
- "we may want to consider removal of this feature in a future language version, and this would be good to deprecate now." [3] slang-pr-11953-dc27a6a
Same as Tess R16 ([137]).

## Files next to this document

- `threads.json`: all 882 human threads with task id and PR number.
- `tess.txt`, `yong.txt`: the two authors' threads, indexed as `[n]`.
- `experts-terms.json`, `experts-stats.json`, `term-counts.json`: the machine-readable outputs.
- `extract.py`, `dump.py`, `stats.py`, `terms.py`, `mkterms.py`, `check.py`: the scripts that produced them.
