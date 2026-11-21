# Glossary Map

The Slang ecosystem has five bounded contexts. Each has its own glossary; the same word can mean different things in two of them, and the "Open ambiguities" section records every such case found so far.

## Contexts

- [Slang Compiler](./slang-compiler/GLOSSARY.md): the internals of `slangc` and the Slang library. Lives in `shader-slang/slang` under `source/`, `include/slang.h`, and `docs/design/`.
- [Slang Language](./slang-language/GLOSSARY.md): what a shader author writes and compiles. Lives in `shader-slang/slang` under `docs/user-guide/` and in the formal specification `shader-slang/spec` (`specification/`, with `proposals/` for adopted features).
- [SlangPy](./slangpy/GLOSSARY.md): the Python library that calls Slang functions on the GPU. Lives in `shader-slang/slangpy` (`docs/`, `slangpy/`).
- [slang-rhi](./slang-rhi/GLOSSARY.md): the C++ render hardware interface. Lives in `shader-slang/slang-rhi` (`include/slang-rhi.h`, `docs/`).
- [Coworker Operations](./coworker-ops/GLOSSARY.md): the fleet of NanoClaw-hosted agents working on the Slang repositories. Lives in the NanoClaw `nv-*` branches (`container/skills`, `container/overlays`, `src/issue-*.ts`, `docs/`) and in `shader-slang/slang-skills` (`skills/*/SKILL.md`).

## Relationships

- **Language → Compiler**: every language construct has a compiler representation with a different name. Conformance becomes a witness table; an interface variant becomes an existential; a generic is specialized by the specialization pass; a shader parameter gets a type layout through parameter binding; a capability requirement is a capability set over capability atoms.
- **Compiler → slang-rhi**: slang-rhi consumes `IComponentType`, the reflection API (`ProgramLayout`, `ParameterCategory`), and `ISyntheticResourceMetadata`. A shader object mirrors a type layout; `ShaderObjectContainerType::ParameterBlock` is the RHI side of a Slang parameter block.
- **Compiler and Language → SlangPy**: SlangPy generates Slang source (an entry point, entry-point uniform parameters, parameter blocks, link-time constants) and compiles it through the Slang API, then reads reflection to build marshalls. `Function.constants` are Slang link-time constants.
- **slang-rhi → SlangPy**: SlangPy's device, buffers, textures, and command encoders are slang-rhi objects exposed through its native layer; `Function.append_to` records into a slang-rhi command encoder.
- **Coworker Operations → all others**: coworkers triage, fix, and review in the slang, slangpy, and slang-rhi repositories; the eval bank's tasks reference those repositories; the compliance check scores posts made to them.

## Open ambiguities

Where the formal specification and `docs/design` disagree, the specification's spelling is canonical for the Slang Language context, and the compiler context keeps its own name for the compiler representation.

1. **launch parameter vs entry-point uniform parameter.** In conversation "launch parameter" means an entry-point `uniform` parameter. The specification uses *launch* only for graphics work (a compute workload is a *dispatch*), and in CUDA "launch parameters" are grid and block dimensions. Canonical: entry-point uniform parameter; count of "launch parameter" in sources is zero.
2. **IR generation vs lower-to-IR.** `docs/user-guide/10-link-time-specialization.md` says "IR generation"; `docs/design/overview.md`, the generated glossary, and the pass's file name say lower-to-IR, while the driving function is `generateIRForTranslationUnit`. Canonical: lower-to-IR.
3. **kernel.** Four senses: (a) loosely, an entry point; (b) per `08-compiling.md`, the compiled output of one entry point on one target; (c) a CUDA kernel, where the word is correct; (d) per the specification, a *compute kernel* is a compute-stage entry point. Canonical: entry point for (a); kernel for (b) and (c); "compute kernel" is accepted specification usage.
4. **backend.** In Slang it is used both for the emitter code and for the target. In slang-rhi it is the per-API implementation layer and is the correct word there. Canonical in Slang: emitter or target as appropriate.
5. **specialization.** Language-level generic specialization (specification), the IR specialization pass, link-time specialization, and Vulkan specialization constants all share the word. The glossaries define the first two separately; a Vulkan specialization constant is never a Slang link-time constant.
6. **conforms to vs implements.** `docs/design/interfaces.md` says a type *implements* an interface; the specification says a type *conforms to* an interface and its members *implement* requirements. Specification wins for the language context.
7. **interface variant vs interface-typed value vs existential.** The specification says *interface-conforming variant* (short: interface variant) and notes that `slangc` calls its type existential; `docs/user-guide/06-interfaces-generics.md` says *interface-typed value*. Decided 2026-11-05: language context says interface-typed value, compiler context says existential; the specification's experimental "interface variant" is noted, not spread.
8. **translation-time constant vs compile-time constant.** The specification's evaluation classes make compile-time constants one subclass of translation-time constants (with link-time and codegen constants); the user guide says compile-time constant for all of them. Specification wins for the language context.
9. **wave vs subgroup; thread group vs workgroup.** The specification uses wave and thread group; SPIR-V-specific user-guide pages use subgroup and workgroup. Canonical: wave, thread group.
10. **thread vs invocation vs lane.** The specification distinguishes an invocation (a unit of work) from the thread that executes it; the user guide uses thread broadly and lane for a position within a wave.
11. **parameter-passing modes** (canonical in both contexts since round 3; "parameter direction" is avoided). The specification lists only `in`, `out`, and `inout`. The compiler also has `BorrowIn` (`__constref`, printed `borrow`) and `Ref` (`__ref`); several proposals use `__constref` in signatures. No specification chapter covers them. Recorded as an open item for the shader-slang/spec maintainers: the compiler's borrow-in parameter (`__constref`, printed `borrow`) and `__ref` have no specification chapter, and several proposals (019, 023, 028) already use `__constref` in signatures.
12. **target compiler vs downstream compiler.** The specification's evaluation-classes chapter says "target compilers"; `docs/design/overview.md` and the source say downstream compiler. The compiler context keeps downstream compiler; the language glossary does not define the term.
13. **session vs Linkage vs global session.** The public `ISession` is implemented by the C++ class `Linkage`; the C++ class `Session` implements `IGlobalSession`. Canonical in prose: session and global session.
14. **layout unit vs parameter category.** The reflection chapter introduces *layout unit* for the concept; the API enum is `ParameterCategory` and most docs use the enum name. Canonical in prose: layout unit.
15. **join point vs merge block.** `docs/design/ir.md` says join point; the source uses merge block in 69 places and join point in 7. Decided 2026-11-05: merge block is canonical in the compiler context; `docs/design/ir.md` should follow.
16. **prelude.** In Slang, a target-specific header prepended to emitted code. In SlangPy, `Function.prelude` is raw Slang source injected into a generated kernel. Unrelated; each glossary defines its own.
17. **heap vs resource heap (slang-rhi).** `IHeap` is a general allocator including the staging heap; `IResourceHeap` is placement memory for aliased resources. "Heap" alone is ambiguous.
18. **fork (coworker ops).** A customized NanoClaw install (defined by its skills recipe) or the `slang-coworkers/slang-eval` repository eval copies push to. Say "eval fork" for the second.
19. **task (coworker ops).** A bank entry (eval task), a NanoClaw scheduled task (`ncl tasks`), or a Harbor-style trial directory. The ops glossary defines the first two.
20. **bot vs coworker; group vs agent group vs messaging group.** The bot is the shared GitHub identity `nv-slang-bot`; a coworker is one agent group. "Group" alone means agent group in ops text, but NanoClaw also has messaging groups.
21. **gate (coworker ops).** A hook gate refuses an action; a script gate decides whether a scheduled task wakes the agent; the issue funnel also speaks of the "human merge gate". The ops glossary defines the first two.
22. **opt-out label vs newcomer label.** The host code names the constant `ISSUE_NEWCOMER_LABELS` and the compliance README says "newcomer label"; the round-1 glossary chose opt-out label because `no-bot` is not a newcomer label. Canonical: opt-out label.
23. **descriptor set.** A Vulkan concept; the Slang reflection *space*; the usual mapping of a Slang parameter block; and an older name for a slang-rhi shader object. Each glossary names the target-neutral concept and lists descriptor set under Avoid.
24. **module.** Slang module, IR module, core module, standard module, precompiled module, and SlangPy `Module` are all in use. The compiler, language, and SlangPy glossaries each define their own sense.
25. **program.** The specification's program is a composition of linkable units; slang-rhi's shader program is `IShaderProgram`; the API's linked program is an `IComponentType`. None of the glossaries uses bare "program" as a term.
26. **dispatch.** The specification's compute dispatch, SlangPy's raw dispatch, slang-rhi's dispatch call, and NanoClaw's "dispatch a task" share the word; each glossary's definition is local to its context.
27. **natural layout: size rounding.** Both maintainers call Slang's platform-neutral default the natural layout. They disagreed (PR 9560) on whether a type's size rounds up to its alignment; the glossary states only the agreed meaning, and the rule is theirs to settle.
28. **capability interface (numerics).** The numerics work (PRs 12859, 13136) says "capability interface" for an interface such as `IScalarNumeric` that marks what a type can do. The word collides with the capability system; use it only with the interface named, and never bare "capability" for it.
