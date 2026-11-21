# Evidence

Usage counts behind every `_Avoid_` entry, the commands that produced them, and the sources read per context. Counts are case-insensitive whole-word match counts (`grep -rhoiE "\b(<pattern>)\b" <files> | wc -l`), so one line with two hits counts twice and identifier hits in code count alongside prose. A count is a signal that the word is in use, not a measure of how often it means the glossary's sense.

## Source sets

| Set | Files |
|-----|-------|
| `D` (Slang docs + public header) | `docs/user-guide/*.md docs/design/*.md docs/*.md CLAUDE.md AGENTS.md include/slang.h` in `/home/haaggarwal/slang` |
| `S` (Slang compiler source) | `source/slang/*.h source/slang/*.cpp` in `/home/haaggarwal/slang` |
| `P` (formal specification) | `ext/spec/specification/*.md` (shallow clone of `shader-slang/spec`) |
| `Q` (proposals) | `ext/spec/proposals/*.md` |
| `Y` (SlangPy) | `ext/slangpy/docs/**`, `ext/slangpy/README.md`, `ext/slangpy/slangpy/**/*.py` |
| `R` (slang-rhi) | `ext/slang-rhi/include/*.h ext/slang-rhi/docs/*.md ext/slang-rhi/README.md ext/slang-rhi/src/*.h` |
| `O` (coworker ops) | `repos/nc-r6/README.md`, `repos/nc-r6/container/skills/*/SKILL.md`, `repos/nc-r6/container/skills/*/README.md`, `repos/nc-r6/container/overlays/*/OVERLAY.md`, `repos/nc-r6/src/issue-opt-out.ts`, `repos/nc-r6/src/issue-stand-down.ts`, `repos/nc-r6/docs/*.md`; some early counts also included `repos/skills-craft/skills/*/SKILL.md` and are marked `O+` |
| `B` (bank review threads) | `tasks/review/*/task.toml`, key `[metadata].threads_json`, in `repos/slang-eval-tasks`: 882 root inline review comments by human maintainers over 315 tasks, extracted to `glossary-draft/experts/threads.json`. A `B` count is the number of threads whose body matches the pattern (case-insensitive regex, `experts/bcounts.py`), not a word count; the Note column lists the task ids. |
| `G` (GitHub review comments and PR descriptions, 2024-11-05 to 2026-11-05) | `glossary-draft/experts/github/github-comments.jsonl`: 3,401 in-window comments by Theresa Foley and Yong He on 762 PRs of `shader-slang/slang`, fetched read-only with `gh api`; plus Tess's 67 authored PR descriptions in `tess-authored-prs.jsonl`. A `G` count is the number of comments whose body matches the pattern (case-insensitive regex, `experts/github/add_terms.py`), not a word count; the Note column lists the PR numbers the entry rests on. |

All `ext/` and `repos/` paths are under `/tmp/claude-1558743079/-home-haaggarwal-slang/1e68114b-25df-4d6b-8c9f-55a4af62c0b3/scratchpad/`.

Command shape, run once per pattern and set:

```bash
grep -rhoiE "\b(<pattern>)\b" <files of the set> | wc -l
```

The one exception is the CUDA-context split for "kernel", which was two line counts:

```bash
grep -rhiE '\bkernel' docs/user-guide/*.md docs/design/*.md | wc -l                 # 84 lines
grep -rhiE '\bkernel' docs/user-guide/*.md docs/design/*.md | grep -ciE 'cuda|optix|ptx|nvrtc'   # 4 lines
```

## Avoid entries and their counts

Where a brief-supplied Avoid term has count 0 in every set, the row says "brief" in the Note column: the term was kept because the round-1 brief reported it in common use, and the zero is recorded so a later round can decide whether to drop it.

### Slang Compiler

| Canonical | Avoid | Pattern | Counts | Note |
|-----------|-------|---------|--------|------|
| lower-to-IR | codegen | `codegen` | D 9, S 41 | canonical `lower(ing)?[- ]to[- ]IR` D 4, S 16 |
| lower-to-IR | IR gen | `IR gen\w*` | D 6, S 19 | |
| lower-to-IR | IR generation | `IR generation` | D 6 | all in `docs/user-guide/10-link-time-specialization.md` |
| specialization | instantiation | `instantiat\w*` | D 9, S 28, P 19 | canonical `specializ\w*` D 210, S 2824, P 49 |
| specialization | monomorphization | `monomorphiz\w*` | D 0, S 0; 3 lines in `docs/generated/design/glossary.md` | the generated glossary has a `[General]` entry for it |
| emitter, target | backend, back-end | `back[- ]?end` | D 49, S 81 | one pattern covers both senses; not split |
| target | platform | `platform` | D 63 | canonical `target` D 631 |
| downstream compiler | backend compiler | `backend compiler` | D 2, S 0 | canonical `downstream compiler` D 34, S 47 |
| downstream compiler | vendor compiler | `vendor compiler` | D 0, S 0 | brief |
| downstream compiler | target compiler | `target compiler` | D 1, S 2, P 3 | spec `expressions-evaluation-classes.md` says "target compilers" |
| prelude | runtime header | `runtime header` | D 0, S 0 | brief |
| prelude | preamble | `preamble` | D 0, S 9 | source hits are unrelated senses; canonical `prelude` D 128, S 65 |
| core module, standard module | stdlib | `stdlib` | D 21, S 10 | canonical `core module` D 53, S 112 |
| core module | standard library | `standard library` | D 6, S 2 | |
| capability atom | capability (bare) | `capabilit(y\|ies)` | D 592 | canonical `capability atom` D 6, S 6 |
| capability atom | feature flag | `feature flag` | D 0, S 0 | brief |
| diagnostic | error message | `error message` | D 7, S 15 | canonical `diagnostic` D 70, S 450 |
| decl-ref | declaration reference | `declaration reference` | D 1, S 21 | |
| decl-ref | DeclRef (in prose) | `DeclRef` | D 22, S 2452 | S hits are the C++ identifier; D hits mix prose and code |
| witness table | vtable | `vtable\|v-table\|virtual function table` | D 6, S 2 | canonical `witness table` D 8, S 206 |
| witness table | conformance table | `conformance table` | D 0, S 3 | |
| existential | interface-typed value | `interface-typed\|interface type` | D 24, P 21 | canonical `existential` D 38, S (not counted) |
| borrow-in parameter | ConstRef | `ConstRef` | D 0, S 28 | identifiers such as `getConstRefParamType`; `BorrowIn` S 42 |
| borrow-in parameter | const ref | `const ref` | D 0, S 0 | brief |
| borrow-in parameter | constref | `__constref` | P 0, Q 5 | proposals 019, 023, 028 use `__constref` in signatures; `docs/generated/design` names it the surface spelling |
| block parameter | phi, phi node | `phi` | D 23, S 243 | canonical `block param\w*` D 1, S 41; D hits are `docs/design/ir.md` explaining the choice |
| join point | merge block, merge point | `merge block\|merge point` | D 0, S 69 | canonical `join point` D 9, S 7; entry marked needs review |
| session | linkage (in API prose) | `linkage` | D 6 | canonical `\bsession` D 105 |
| layout unit | parameter category (in prose) | `parameter category\|ParameterCategory` | D 58, S 18 | canonical `layout unit` D 16, S 6; the API enum keeps its name |
| parameter-passing mode | parameter direction | `parameter direction` | B 0, D 0, S 19 | round 3 (experts); S hits are comments using the specification's word; canonical `param(eter)?[- ]passing mode` B 10 (Tess), S 37; slang-pr-13213-84be79e, slang-pr-13401-c99f962, slang-pr-13406-66523f1 |
| parameter-passing mode | passing convention | `passing convention` | B 0, D 0, S 0 | maintainer-supplied |
| bytes | uniform (meaning bytes) | `uniform` | B 11 | not sense-split (the keyword and `LayoutResourceKind::Uniform` share the word); Tess's corrections in slang-pr-11135-d240653, slang-pr-12306-75e037d; canonical `bytes\|byte-granularity` B 22 |
| bytes | uniform usage | `uniform (field )?usage` | B 1, D 0, S 2 | slang-pr-11135-d240653 |
| effective `this` parameter | declared mode (when the computed one is meant) | `declared .* mode` | B 3 | slang-pr-13213-84be79e, slang-pr-13401-c99f962; canonical `effective.*this\|effectively static` B 6 |
| disposition | check (as a noun for the result) | `as a "check"` | B 1, D 0, S 0 | slang-pr-12596-1dbdab4; canonical `disposition\|verdict` B 6 (slang-pr-12596-1dbdab4, slang-pr-12596-5553973) |
| internal error | fallback | `fallback` | B 8, D 26, S 127 | not sense-split; Tess slang-pr-11135-d240653; canonical `internal error\|assert-fail\|loud error` B 6 (slang-pr-11798-5f4a206, slang-pr-12252-5915b22 by Yong; slang-pr-11135-d240653, slang-pr-12544-479e4da by Tess) |
| internal error | defensive handling | `defensive` | B 3, D 1, S 19 | slang-pr-11135-d240653, slang-pr-12421-8cd02a1, slang-pr-13539-7228ad1 |
| cumulative offset | absolute offset | `absolute` (B), `absolute offset` (D, S) | B 3, D 1, S 0 | Tess slang-pr-12715-6f2f414; other reviewers in slang-pr-12116-3a7b41a, slang-pr-12717-5dbb25c; canonical `cumulative offset` B 2, D 13 |
| cumulative offset | reflection offset | `reflection offset` | B 1, D 0, S 0 | slang-pr-12715-6f2f414 |
| index into | select from an array, array selection | `array selection\|select(ion)? from .*array` | B 1, D 0, S 0 | slang-pr-13539-7228ad1; canonical `index into` D 3, S 12 |
| subject (of a modifier) | target (for the modified construct) | `target.*modif\|modif.*target` | B 1 | slang-pr-12596-5553973; `target` D 631 is the compilation-target sense |
| early-out | bail-out | `bail[- ]?out` | B 3, D 1, S 43 | slang-pr-13539-7228ad1, slang-pr-13283-a3dd7e7; canonical `early[- ]out` B 12, S 17 |
| early-out | guard (for the statement itself) | `guard` (B), `guard clause` (D, S) | B 13, D 0, S 0 | B not sense-split (most hits are "guard against"); slang-pr-12596-5553973 and nine other tasks |
| effective source language | allow GLSL | `allow(ed\|s)? GLSL\|AllowGLSL` | G 12 | PRs 12836; canonical `source language` G 9 |
| witness | proved (for solving a witness) | `\bproved?\b` | G 20 | PRs 11210, 9628, 11368; canonical `\bwitness` G 123 |
| refinement | conformance (for interface-to-interface) | `conformance witness` | G 5 | PRs 13885, 12555; canonical `refine` G 8 |
| refinement | subtype witness (for a refinement) | `SubtypeWitness` | G 13 | PRs 13885, 12555 |
| shadow variable | compatibility variable | `compatibilityVar\|compatibility variable` | G 3 | PRs 13445; canonical `\bshadow` G 38 |
| shadow variable | source global | `source global` | G 3 | PRs 13445 |
| abstract storage | location (bare) | `\blocation\b` | G 92 | PRs 13506, 13406; canonical `storage location\|memory location` G 16 |
| default-value expression | default expression | `default expression` | G 2 | PRs 11210; canonical `default-value expression\|default( generic)? argument` G 15 |
| default-value expression | real default | `real default` | G 2 | PRs 11210 |
| sub and sup type | endpoint | `\bendpoints?\b` | G 10 | PRs 11368; canonical `\bsub/sup\|\bsup\b` G 12 |
| pointee type | target type (of a pointer) | `target/\"pointee\"\|target type` | G 5 | PRs 7678; canonical `pointee` G 3 |
| immutable location | immutable (when only read-only is meant) | `\bimmutable\b` | G 41 | PRs 8526, 9881, 8433; canonical `read-only\|readonly` G 40 |
| post-emit metadata | side-band file (for reporting) | `side-band` | G 1 | PRs 10886, 10896, 10076; canonical `post[- ]?emit metadata\|PostEmitMetadata` G 6 |
| descriptor kind | Texture_Read, Buffer_ReadWrite | `Texture_Read\|Buffer_ReadWrite` | G 2 | PRs 8252; canonical `SampledImage\|StorageBuffer` G 8 |

### Slang Language

| Canonical | Avoid | Pattern | Counts | Note |
|-----------|-------|---------|--------|------|
| precompiled module | binary module, IR module (user-facing) | `slang-module\|precompiled module\|IR module\|binary module` | D 56 | combined pattern, not split |
| link-time constant | specialization constant | `specialization constant` | D 3, P 5 lines | spec uses it for the Vulkan feature |
| translation-time constant | compile-time constant (for the class) | `compile-time constant` | D 9, S 20, P 12 | canonical `translation-time` D 0, P 6 |
| entry point | kernel (outside CUDA text) | `kernel` | D 78 (84 lines, 4 in CUDA context), S 58, P 13 | P hits are "compute kernel"; canonical `entry point` D (not counted), P 28 |
| entry point | main function | `main function` | D 0 | brief; `02-conventional-features.md` notes GLSL requires `main` |
| entry-point uniform parameter | kernel parameter | `kernel parameter` | D 0 | brief |
| entry-point uniform parameter | launch parameter | `launch parameter` | D 0 | brief; canonical `entry[- ]point uniform` D 3, S 5 |
| binding semantic | semantic (bare) | `semantic` | D 123, P 29 | |
| thread | invocation (for the thread) | `invocation` | D 38, P 30 | spec distinguishes the two |
| wave | subgroup | `subgroup` | D 23, S 9, P 0 | canonical `wave` D 67; spec `wave\|subgroup` 72, all wave |
| thread group | workgroup, work group | `workgroup\|work group` | D 7, S 23, P 0 | canonical `thread group` D 2, P 31 |
| dispatch | launch (for compute work) | `launch` | D 13, P 16 | spec uses launch for graphics work only |
| parameter block | descriptor set | `descriptor set` | D 28, S 21, P 0 | canonical `parameter block` D 27, S 28, P 4 |
| parameter block | constant buffer (when the construct is meant) | `constant buffer` | D 67, S 112, P 5 | |
| space | register space | `register space` | D 9 | |
| space | descriptor set | see above | | |
| capability requirement | capability (bare) | `capabilit(y\|ies)` | D 592 | canonical `capability requirement` D 6, S 3 |
| conformance | implements an interface | `implement\w* (the \|an \|a )?interface` | D 18; P 3 lines | spec `declarations.md:319` says a struct "implements the required members"; `conform\w*` D 99, P 72 |
| generic | template | `template` | D 16, S 841 | S hits are C++ templates |
| interface variant | interface-typed value | `interface-typed\|interface type` | D 24, P 21 | spec `interface(-conforming)? variant` P 18 |
| interface variant | existential value | `existential` | D 38, P 2 | |
| parameter-passing mode | parameter direction, passing convention | see the compiler table | | round 3: entry renamed from "Parameter direction"; the specification's `declarations.md` still says "parameter directions" |
| error | exception | `exception` | B 14, D 14, S 64 | Tess asks for "error" in slang-pr-12209-695f596; most other B, D, and S hits are C++ exceptions |
| error | throw an exception (in prose) | `throw` | B 9 | the `throw` keyword itself stays; slang-pr-12209-695f596 prefers "raising" in prose |
| readonly ref access | const (as the ref access qualifier) | `` `const` `` | B 2 | slang-pr-13406-66523f1 (Tess), slang-pr-13406-a1286c3; canonical `readonly` B 7, D 4, S 21 |
| language version | module version | `module version` | B 2, D 11, S 3 | Yong "user module version" in slang-pr-12151-f0371d1; slang-pr-12963-90a6877; D hits are the `.slang-module` format version, a different sense; canonical `language version` B 7, D 17, S 28 |
| language version | dialect (for the version) | `dialect` | B 1, D 0, S 7 | slang-pr-12596-5553973 |
| dialect | HLSL mode, GLSL mode | `(HLSL\|GLSL) mode` | G 6 | PRs 13506, 12836, 13958, 13113; canonical `dialect` G 29 |
| dialect | supports GLSL | `supports? GLSL` | G 1 | PRs 13506, 12836, 13958, 13113 |
| dialect | allow GLSL | `allow(ed\|s)? GLSL\|AllowGLSL` | G 12 | PRs 13506, 12836, 13958, 13113 |
| export | public (for linkage) | `public __extern_cpp\|PublicDecoration` | G 2 | PRs 12242, 12304, 7447; canonical `\bexport\b` G 10 |
| static const | constexpr (in user documentation) | `constexpr` | G 7 | PRs 10455; canonical `static const` G 11 |
| address space | storage class | `storage class` | G 1 | PRs 10657, 11709, 7678; canonical `address space` G 19 |
| combined texture-sampler pair | combined texture sampler | `combined texture sampler\b` | G 1 | PRs 6028; canonical `texture-sampler pair` G 2 |
| proper type | value type (for this notion) | `value type` | G 10 | PRs 12585, 12555, 13885, 10165, 11210; canonical `proper type` G 22 |
| contract | single interface (when a conjunction is allowed) | `single interface` | G 1 | PRs 13885; canonical `\bcontract\b` G 112 |
| enum declaration | enum class (in the core language) | `enum class` | G 4 | PRs 11044; canonical `\benum\b` G 49 |
| take the address | take pointer | `take pointer` | G 2 | PRs 7848, 9881; canonical `take (the )?address\|getAddress` G 9 |
| cast | cast (for an implicit conversion) | `\bcast(s\|ing)?\b` | G 45 | PRs 6028; canonical `\bconversion` G 59 |

### SlangPy

| Canonical | Avoid | Pattern | Counts | Note |
|-----------|-------|---------|--------|------|
| vectorized call, raw dispatch | kernel launch, launch | `kernel launch\|launch(es\|ed\|ing)? (the\|a\|it\|kernels?)` 6; `launch\w*` 20 | Y | canonical `dispatch` family 494, `vectoriz\w*` 221 |
| Tensor | NDBuffer | `NDBuffer` | Y 33 | all in `docs/tensorupdate.rst` and migration notes; removed in 0.41 |
| Tensor | TensorView | `TensorView` | Y 273 | includes deprecated Slang type names still present in code and docs |
| Tensor | DiffTensorView | `DiffTensorView` | Y 114 | |

### slang-rhi

| Canonical | Avoid | Pattern | Counts | Note |
|-----------|-------|---------|--------|------|
| device type | backend (for the enum value) | `backend` | R 91 | "backend" is also the canonical word for the implementation layer |
| shader object | descriptor set | `descriptor set` | R 1 | canonical `shader object` R 23 |
| heap | resource heap (for `IHeap`) | `resource heap` | R 4 | the phrase itself is canonical for `IResourceHeap` |
| resource heap | heap (bare, for placement) | `heap` | R 178 | |
| surface | swapchain, swap chain | `swap ?chain` | R 2 | canonical `surface` R 30 |
| command encoder, command buffer | command list | `command list` | R 7 | hits are D3D12 native-handle comments |
| pipeline | pipeline state | `pipeline state` | R 2 | canonical `pipeline` R 179 |
| internal reference | weak reference | `weak reference` | R 1 | `docs/object-lifetime.md` states it is not one |

### Coworker Operations

| Canonical | Avoid | Pattern | Counts | Note |
|-----------|-------|---------|--------|------|
| coworker | bot (for a coworker) | `\bbot\b` | O 139 | canonical `coworker` O 149; `\bagent\b` O+ 1566 is NanoClaw's generic word and was not listed |
| coworker type | role template | `role.template` | O 1 | `docs/USAGE.md` calls v1 "the monolithic role-template system" |
| orchestrator | main group, admin group | `main group\|admin group` | O 6 | canonical `orchestrator` O 83 |
| thread | session (for the shared topic) | `session` | O 680 | not split by sense; `docs/thread-vs-session.md` documents the confusion |
| opt-out label | newcomer label | `newcomer label` | O 5 | host constant `ISSUE_NEWCOMER_LABELS`; compliance README R6 |
| opt-out label | bot-ok | `bot-ok` | O 0 | brief |
| driver | harness | `harness` | O 4 | canonical `driver` O 85, but most hits are other senses (GPU driver, cost driver) |
| eval copy | evaluation copy | `evaluation copy` | O 2 | canonical `eval copy` O 8 |
| eval sandbox | gym | `gym` | O 0 | operator shorthand recorded in the user's memory notes, not in sources |
| eval sandbox | sandbox (bare) | `sandbox` | O 32 | canonical `eval sandbox\|eval-sandbox` O 5 |
| trial | attempt | `attempt` | O 12 | eval-runner uses "attempt 2" for a retried trial |
| cost cap | budget (for the cap mechanism) | `budget` | O 81 | canonical `cost cap\|cost-cap` O 37 |
| spine | provider document | `provider document` | O 2 | `self-customize/SKILL.md` "composed provider document (`CLAUDE.md` or `AGENTS.md`)"; canonical `spines?` O 66, which also counts the funnel's "PR spine" in `docs/issue-funnel-design.md` |
| spine | system prompt (for the composed file) | `system prompt` | O 11 | hits mix the composed file (`docs/ollama.md`) with the runner's memory addendum and per-call LLM prompts |
| trait | capability name | `capability names?` | O 1 | the gloss `docs/lego-coworker-workflows.md` gives for trait; canonical `traits?` O 23 |
| trait | capability (bare) | `capabilit(y\|ies)` | O 48 | most hits are "capability skill", a kind of skill, not a trait |
| composer | template system | `template system` | O 2 | `docs/USAGE.md` "Lego coworker template system"; canonical `composer` O 22 |
| composer | spine renderer (for the whole module) | `spine renderer` | O 1 | one of the composer's three parts in `docs/lego-coworker-workflows.md` (registry, resolver, spine renderer) |
| learning | atom | `atoms?` | O 102 | `learnings-wiki/SKILL.md` layer word for a raw L1 learning file, kept generic so other knowledge bases reuse the skill; canonical `learnings?` O 157 |
| credential gateway | OneCLI (for the concept) | `onecli` | O 91 | the current provider; `docs/gateway-seam.md` makes the gateway pluggable; canonical `credential gateway` O 16 |
| credential gateway | vault, Agent Vault | `vault` | O 15 | `agent vault` O 3 within; `README.md` "OneCLI's Agent Vault" |
| credential gateway | credential proxy | `credential proxy` | O 3 | `docs/REQUIREMENTS.md` heading "OneCLI Credential Proxy" |

## Removed entries

- **buddy** (coworker ops), removed 2026-11-05. The maintainer challenged it: "we don't use this, it is disabled". The `buddy-monitor` overlay and `buddy/SKILL.md` still exist in `repos/nc-r6` (`buddy` O 30, `companion( monitor)?` O 3), so the counts stay recorded here; the entry and its Avoid "companion monitor" are gone from `coworker-ops/GLOSSARY.md`.

## Terms taken from a proposal that is not yet in the specification

- **borrow-in parameter** (compiler): `__constref` appears only in proposals 019 (cooperative vector, Implemented), 023 (cooperative matrix, Implemented), and 028 (cooperative matrix 2) and in compiler source; no specification chapter defines the passing mode.
- **dynamic uniform** (language): from `docs/user-guide/a1-05-uniformity.md`; the specification has no uniformity-analysis chapter.
- **capability requirement**, **profile** (language): from `docs/user-guide/05-capabilities.md` and `08-compiling.md`; the specification mentions "capabilities" once.
- **derivative function**, **differential pair** (language): from `docs/user-guide/07-autodiff.md`; the specification has no automatic-differentiation chapter. Proposal 010 (new differentiable type system) covers the type side.
- **precompiled module** (language): from `docs/user-guide/08-compiling.md` and `10-link-time-specialization.md`; the specification's translation overview lists linking and specialization phases but names no file format.
- **interface variant** (language): in the specification (`types-interface.md`, marked experimental), not in the user guide.

## Sources read per context

### Slang Compiler
- `/home/haaggarwal/slang/docs/design/overview.md`, `ir.md`, `decl-refs.md`, `interfaces.md`, `semantic-checking.md`, `existential-types.md`, `capabilities.md`, `stdlib-intrinsics.md` (first 80 lines), headings of `autodiff.md`, `serialization.md`, `backwards-compat-for-ir-modules.md`
- `/home/haaggarwal/slang/docs/generated/design/glossary.md` (77 entries; input, not truth)
- `/home/haaggarwal/slang/CLAUDE.md`, `AGENTS.md`, `.github/copilot-instructions.md`
- `/home/haaggarwal/slang/include/slang.h`: interface list, enum list, `IComponentType` and `ISession` doc comments, `SlangParameterCategory`
- `/home/haaggarwal/slang/source/slang/slang-capabilities.capdef` (header comment), `slang-diagnostics.lua` (header), `slang-ast-support-types.h` (`ParamPassingMode`), and the file-level comments of `slang-ir-link.h`, `slang-ir-specialize.h`, `slang-compiler.h`, `slang-check.h`, `slang-ir-inline.h`, `slang-ir-dce.h`, `slang-mangle.h`, `slang-type-layout.h`, `slang-parameter-binding.h`, `slang-ir-util.h`, `slang-ast-decl.h`, `slang-ast-type.h`, `slang-ir-glsl-legalize.h`, `slang-ir-entry-point-uniforms.h`, `slang-ir-explicit-global-context.h`, `slang-ir-any-value-marshalling.h`, `slang-ir-check-differentiability.h`

### Slang Language
- `/home/haaggarwal/slang/docs/user-guide/`: headings of every chapter; full or sectional reads of `02-conventional-features.md` (parameters, shader parameters, entry points), `04-modules-and-access-control.md`, `05-capabilities.md`, `07-autodiff.md` (overview and type system), `08-compiling.md` (concepts), `09-reflection.md` (spaces), `09-targets.md` (terminology), `10-link-time-specialization.md`, `a1-05-uniformity.md`
- Specification: `glossary.md`, `shaders-and-kernels.md`, `basics-translation-overview.md`, `basics-program-execution.md`, `types-interface.md` (interface-conforming variants, dispatch mechanism), `types-this.md`, `expressions-evaluation-classes.md`, `generics.md` (description), `declarations.md` (parameter directions, conformance, specialization), `basics-name-lookup.md` and `basics-scope.md` (TODO stubs), plus headings of the remaining chapters
- Proposals: `README.md`, status lines of all proposals, `__constref` occurrences in 019, 023, 028

### SlangPy
- `README.md`; `docs/src/basics/firstfunctions.rst`, `broadcasting.rst`, `mapping.rst`, `nested.rst`, `returntype.rst`, `typemethods.rst`, `index_representation.rst`, `linktime.rst`, `tensors.rst`; `docs/src/generators/generators.rst`, `generator_call_groups.rst`; `docs/src/autodiff/autodiff.rst`; `docs/tensorupdate.rst`; headings of `docs/src/tensors/*.rst`
- Package docstrings extracted with `ast`: `slangpy/core/function.py` (`FunctionNode` methods), `module.py`, `struct.py`, `instance.py`, `calldata.py`, `callsignature.py`, `generator.py`, `packedarg.py`; `slangpy/bindings/marshall.py`, `boundvariable.py`, `typeregistry.py`, `codegen.py`; `slangpy/types/diffpair.py`, `types/__init__.py`; `slangpy/__init__.py`

### slang-rhi
- `README.md`; `docs/object-lifetime.md`, `resource-heaps.md` (headings), `synthetic-bindings.md`, `error-handling.md`
- `include/slang-rhi.h`: interface class list, struct and enum list, `DeviceType`, `LinkingStyle`, `ShaderProgramDesc`, `DescriptorHandle`, `ShaderOffset`, `ShaderObjectContainerType`, heap and resource-heap comments, encoder comments

### Coworker Operations
- `repos/nc-r6/README.md`; `container/overlays/{buddy-monitor,critique-gate,eval-sandbox,plan-gate,review-length}/OVERLAY.md`; `container/skills/eval-runner/{SKILL,README}.md`; `container/skills/compliance-check/{SKILL,README}.md`; `container/skills/{base-nanoclaw,buddy,codex-critique,supervise-issues,onecli-gateway,learnings-wiki,okf-synthesis,welcome,self-customize,review-cycle-mining,explain-diff-html}/SKILL.md` (full or head); `src/issue-opt-out.ts` and `src/issue-stand-down.ts` header comments
- `repos/nc-r6/docs/`: `USAGE.md` (lego model, coworker types, session modes), `lego-coworker-workflows.md`, `cost-cap-model.md`, `thread-vs-session.md`, `isolation-model.md`, `architecture.md` (groups vs sessions), `critique-gate-boundaries.md`, `skills-model.md`, `issue-funnel-design.md`, `BRANCH-FORK-MAINTENANCE.md`, `REQUIREMENTS.md` (deployment), `gateway-seam.md`, `memory.md`, `mcp-allowlist.md` (grep for `append_learning`)
- `repos/skills-craft/skills/*/SKILL.md`: names and descriptions of all 31 skills; heads of `slang-evaluate-session`, `slang-maintainer-tools`, `human-names`

### Bank review threads (set B, round 3)
- All 231 threads by Theresa Foley (`tangent-vector`) and 13 by Yong He (`csyonghe`), read in full; the other 638 human threads were only pattern-counted. The reading, term counts, corrections, and rules are in `experts/EXPERTS.md`; the candidate list is `experts/experts-terms.json`; the terms added from it are listed in `experts/experts-added.json`.
- Round-3 additions: 12 compiler terms (parameter-passing mode, effective `this` parameter, disposition, subject, internal error, index into, bytes, cumulative offset, documentation comment, implementation comment, early-out, workaround) and 5 language terms (readonly ref access, language version, operator, tuple construction, error); "Parameter direction" renamed to "Parameter-passing mode". Convention items from the candidate list (`calc`/`compute` prefix, "collect" as the verb) and the standard-module-library naming went to guidelines, not the glossary. The binding-semantic soft conflict (Tess uses bare "semantics" in compiler prose) got no Avoid: the compiler glossary has no binding-semantic entry to attach it to.

### GitHub review comments (set G, round 4)
- All in-window comments by Theresa Foley (1,427 recent-year, 366 older-year) and Yong He (895 recent-year, 713 older-year) on 762 PRs, read in full by chunked readers; terms, corrections, and rules are in `experts/github/GITHUB-EXPERTS.md`, the candidate list in `experts/github/github-terms.json`, and the terms added from it in `experts/github/github-added.json`.
- Round-4 additions: 21 compiler terms (effective source language, experimental module, witness, refinement, facet, lookup breadcrumb, shadow variable, abstract storage, default-value expression, candidate frontier, sub and sup type, publication, unit type, dedicated opcode, peephole pass, pointee type, immutable location, post-emit metadata, descriptor kind, predicate, bottleneck) and 12 language terms (dialect, export, internal, `static const`, address space, combined texture-sampler pair, proper type, contract, enum declaration, logical scalar, take the address, cast). The six "conflicts" candidates (borrow versus copy-in/copy-out, front end versus back end, compile-time versus translation-time constant, capability interface, natural layout, unit type's older spelling) are left for the maintainer; unit type itself was added as a plain entry. Convention candidates (accessor verbs, acronym casing, `InBytes` suffix, size versus count, argument versus parameter value) and review vocabulary were not added, except predicate and bottleneck.
