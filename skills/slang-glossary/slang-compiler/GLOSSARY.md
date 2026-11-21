# Slang Compiler

The internals of `slangc` and the Slang library: how source text becomes an AST, Slang IR, and target code. Terms here name compiler data structures and pipeline steps, not the language features a shader author sees.

## Compilation units and pipeline

**Compile request**:
One invocation of the compiler: its options, translation units, entry points, and targets. The public API spells it `ICompileRequest`; the C++ type is `CompileRequest`.

**Translation unit**:
A group of source units that are checked together as one namespace. Compiling a translation unit produces one module.

**Module**:
The compiled result of one translation unit: a checked AST plus an IR module. A module is loaded by `import` or from a `.slang-module` file.

**Lower-to-IR**:
The step that walks a checked AST and produces the IR module for one translation unit. It runs once per translation unit and never depends on a target.
_Avoid_: codegen (for this step), IR gen, IR generation

**Linking**:
The back-end step that copies an entry point and its dependencies into a fresh IR module, picking the best target-specific definition of each symbol. Prelinking is the earlier, target-independent copy of `[__unsafeForceInlineEarly]` symbols.

**Specialization**:
The IR pass that replaces generic parameters and interface lookups with concrete types, values, and witness tables. After it, no user generic or interface remains unless dynamic dispatch was requested.
_Avoid_: instantiation, monomorphization (as the pass name)

**Type legalization**:
The IR pass that splits an aggregate type mixing ordinary data and resources into separate declarations, so that targets with strict rules accept the program.

**Front end**:
The half of the compiler through lower-to-IR: parsing, semantic checking, and lowering. It owns validity and policy; a diagnostic or a mode decision is made here, once.

**Back end**:
The half of the compiler after lower-to-IR: the IR passes, linking, legalization, and the emitters. It reads only the IR and never consults front-end options or the AST.
_Avoid_: backend (for the target or for the emitter alone), back-end

**Emitter**:
The per-target code in `slang-emit-*.cpp` that turns legalized IR into HLSL, GLSL, SPIR-V, Metal, WGSL, CUDA, or C++ output.
_Avoid_: backend (when the emitter alone is meant)

**Target**:
One desired output of a compile request: a code format plus a profile, capability set, and options. The API spells it `TargetDesc`; internally it is `TargetRequest`.
_Avoid_: backend (for the target itself), platform

**Downstream compiler**:
An external compiler that Slang invokes on its emitted output, such as DXC, fxc, glslang, NVRTC, or the Metal compiler.
_Avoid_: backend compiler, vendor compiler, target compiler

**Pass-through**:
A mode in which Slang skips its own pipeline and hands source text straight to a downstream compiler. It exists as a debugging aid.

**Prelude**:
A target-specific header that Slang prepends to emitted CPU, CUDA, HLSL, or Torch code so the output can use Slang-defined helpers. Preludes live under `prelude/` and are not language built-ins.
_Avoid_: runtime header, preamble

**Core module**:
The built-in module, written in Slang in `source/slang/*.meta.slang`, that defines the fundamental types and intrinsics available to every program without `import`.
_Avoid_: stdlib, standard library

**Standard module**:
A module shipped separately as a `.slang-module` file next to the compiler, such as `neural` or `numerics`, and loaded only when imported.
_Avoid_: stdlib

**Target intrinsic**:
A core-module declaration whose body is a per-target expansion given by `__target_intrinsic`, so the emitter writes target code directly instead of lowering a Slang body.

**Capability atom**:
One named target, stage, version, or extension feature defined in `slang-capabilities.capdef`; the smallest unit of the capability system.
_Avoid_: capability (when one atom is meant), feature flag

**Capability set**:
A disjunction of conjunctions of capability atoms. The runtime representation stores one atom set per target and stage, so merging disjuncts is lossy.

**Diagnostic**:
A message the compiler reports to a `DiagnosticSink` with a numeric code and a severity of note, warning, error, or fatal. Definitions live in `slang-diagnostics.lua`.
_Avoid_: error message (when a warning or note may be meant)

**Internal error**:
The failure raised when a shape an earlier phase should have removed or guaranteed reaches a later phase, such as an unlowered type at emit. It is asserted, not handled: the producing phase is fixed and the consumer never patches the shape.
_Avoid_: fallback, defensive handling (for an out-of-contract shape)

**Effective source language**:
The one language whose scope, parser mode, and semantic rules apply to a translation unit, chosen once before parsing. Its provenance, an option, file extension, or `#language` directive, supports diagnostics only.
_Avoid_: allow GLSL (the dialect is selected, not allowed)

**Experimental module**:
A standard module under `experimental/`, imported explicitly as `import experimental.<name>`, whose contents may change or disappear without a deprecation period.

## Front-end representation

**Decl-ref**:
A reference to a declaration together with the substitutions needed to read it in context, such as `Cell<int>::value`. The C++ type is `DeclRef<T>`.
_Avoid_: declaration reference, DeclRef (in prose)

**Substitution**:
A mapping applied through a decl-ref that fills in generic arguments or the concrete `This` type of an interface member.

**Witness table**:
The record of how a type conforms to an interface: one entry per requirement, keyed by requirement, naming the implementing member. The IR carries it as a `WitnessTable` instruction.
_Avoid_: vtable, conformance table

**Existential box**:
The compiler's representation of a value whose static type is an interface contract: a box holding a concrete type, a value, and a witness table. The type is `ExistentialBoxType`; the packing expression is `MakeExistentialBoxExpr`, and older code says `makeExistential`.
_Avoid_: existential (bare, when the box type is meant), interface-typed value (in compiler prose)

**Parameter-passing mode**:
The `ParamPassingMode` a parameter is passed with: `in`, `out`, `inout`, borrow-in, or ref. The compiler treats `inout` as an exclusive mutable borrow and borrow-in as an immutable borrow; the front end computes the mode once.
_Avoid_: parameter direction, passing convention

**Borrow-in parameter**:
A parameter passed as a reference to an immutable borrowed value, `ParamPassingMode::BorrowIn`. It is spelled `__constref` in source and printed as `borrow T`.
_Avoid_: ConstRef, const ref, constref

**Effective `this` parameter**:
The implicit `this` parameter a declaration has after its ancestors and context are applied, with its type and parameter-passing mode. A static or effectively static declaration has none; `[mutating]`, `set` accessors, `class` types, and `extension`s change the mode or type.
_Avoid_: declared mode (when the computed mode is meant)

**Disposition**:
The result of a validity check, such as whether a modifier is allowed on a declaration: allowed, error, warning-or-error by language version, or no verdict. Diagnosing is a separate step that reads the disposition.
_Avoid_: check (as a noun for the result)

**Subject (of a modifier)**:
The declaration or syntax node a modifier applies to. "Target" is reserved for a compilation target.
_Avoid_: target (for the modified construct)

**Witness**:
The value that proves a conformance, coercion, or type equality; the solver finds or infers it, and source code never spells one. A routine that finds a witness returns the witness, not a Boolean.
_Avoid_: proved (for solving a witness)

**Refinement**:
The relation between two interfaces when one inherits the other's requirements, proved by a refinement witness. It is neither a proper type's conformance nor a subtype relation.
_Avoid_: conformance (for interface-to-interface), subtype witness (for a refinement)

**Facet**:
One entry in a type's flattened inheritance information, used for member lookup. When the looked-up subject and the entry both have types, the facet carries the proof relating them.

**Lookup breadcrumb**:
An implicit step that expression construction inserts to reach a member found by lookup. Examples: `ThisExpr` for an implicit `this` or `ThisType` for the enclosing type.

**Shadow variable**:
The compiler-created declaration that lookup finds under a uniform parameter's original name when `-Gec` compatibility is on. It is an immutable alias or, when the parameter is written, mutable storage.
_Avoid_: compatibility variable, source global

**Abstract storage**:
A property or user-defined subscript whose value comes from `get`, `set`, or `ref` accessors rather than an address. An abstract storage location is the general notion; a memory location is the addressable case.
_Avoid_: location (bare)

**Default-value expression**:
The expression a generic or function parameter declares as its default argument value. It is evaluated or reduced once its dependencies resolve; it does not run.
_Avoid_: default expression, real default

**Candidate frontier**:
The overload candidates still tied after ordinary ranking, `OverloadResolveContext::bestCandidates`. Compatibility policy applies to the frontier last, so it never pre-empts later ranking rules.

**Sub and sup type**:
The two sides of a type constraint `sub : sup`: the constrained type and the interface or type it must satisfy.
_Avoid_: endpoint

**Publication**:
The point at which a synthesized declaration is committed as a witness or ordinary member; speculative candidates are never published. Its root is the outermost declaration that owns the synthesized graph.

**Unit type**:
Compiler prose for the canonical type with exactly one value, which Slang source spells `void`.

## IR

**IR instruction**:
The single node type of Slang IR: an opcode, a type, operands, decorations, and children. Types, constants, functions, blocks, and the module itself are all instructions.

**Hoistable instruction**:
An instruction whose value depends only on its operands. It is deduplicated and placed at the outermost scope where its operands are available.

**Decoration**:
A child instruction that attaches non-essential metadata to another instruction, such as a name hint, a layout, or a target-intrinsic spelling.

**Block parameter**:
An `IRParam` at the head of a block that receives a value from each predecessor's branch arguments. Slang IR uses block parameters instead of phi instructions.
_Avoid_: phi, phi node

**Merge block**:
The block where control flow reconverges after a structured branch, stored as an operand of the branch so emitters can rebuild `if` and loop statements.
_Avoid_: join point, merge point

**Index into**:
Reading one element of an array by position: code indexes into, subscripts, or gets an element from an array. `select` is the IR instruction that chooses between two values by a condition, never array access.
_Avoid_: select from an array, array selection

**Dedicated opcode**:
An IR instruction kind, `kIROp_...`, introduced for each concept a later pass must recognize, such as `CoopMatMulAdd` or `ImageLoad`. Passes never recover a concept from names, decorations, or emitted text.

**Peephole pass**:
The `PeepholeOptimize` pass: a pure local simplifier that emits no diagnostics. Round-trip casts fold to their inner operand there, and backward peepholes belong there rather than in bespoke passes.

**Pointee type**:
The type a pointer type points to.
_Avoid_: target type (of a pointer)

**Immutable location**:
A memory location that is read-only and exclusive, so optimizations may reorder or merge its loads. Read-only alone grants a permission and promises nothing about other writers.
_Avoid_: immutable (when only read-only is meant)

## API objects and layout

**Session**:
The public `ISession`: a scope holding loaded modules, search paths, and targets. Its C++ class is `Linkage`; the coarser `IGlobalSession` owns the core module and downstream-compiler discovery.
_Avoid_: linkage (in API-facing prose)

**Component type**:
A unit of composition, `IComponentType`: a module, an entry point, a type conformance, or a composite of these. Linking a composite yields the program whose kernels are requested.

**Type layout**:
The target-dependent description of how much of each layout unit a type consumes and where its fields and elements sit.

**Natural layout**:
Slang's platform-neutral default layout for a type. It gives each field its byte offset and the type its size and alignment, before any target layout applies.
_Avoid_: C layout (for the default), compatible layout (for the default)

**Layout unit**:
One kind of resource a parameter can consume, such as bytes, `t` registers, or descriptor-table slots. The API enum is `ParameterCategory`.
_Avoid_: parameter category (in prose)

**Bytes**:
The layout unit, `LayoutResourceKind::Uniform`, in which buffer contents, payloads, and other memory-backed data are measured. New code says bytes or byte-granularity; "uniform" is the legacy enum name only.
_Avoid_: uniform (meaning bytes), uniform usage

**Parameter binding**:
The per-target step that assigns registers, bindings, and byte offsets to every shader parameter of a composed program, honoring explicit `register` and `[[vk::binding]]` markup first.

**Cumulative offset**:
The offset of a nested field or element relative to the start of its enclosing container, summed along the access path through reflection. Every offset is relative to something; an offset inside a constant buffer is cumulative, not absolute.
_Avoid_: absolute offset, reflection offset

**Post-emit metadata**:
The `IArtifactPostEmitMetadata` record of facts about emitted code, such as the bindings a kernel uses, that an application queries through a dedicated API. The compiler never reports such facts by writing files.
_Avoid_: side-band file (for reporting)

**Descriptor kind**:
The kind of binding a parameter occupies on a target, named after the Vulkan descriptor type: `SampledImage`, `StorageBuffer`, `UniformTexelBuffer`, `ConstantBuffer`.
_Avoid_: Texture_Read, Buffer_ReadWrite

## Codebase and review vocabulary

**Documentation comment**:
The comment attached to a declaration, written with `///` or `//`, that states what the abstraction does and its behavioral contract for a client. It never describes implementation strategy, history, or open issues.

**Implementation comment**:
A comment inside a body, for a future maintainer, explaining the problem solved, the solution strategy, the invariants relied on, and rejected alternatives. It is written in declarative voice with authorial "we" and never cites issues or PRs.

**Early-out**:
A `return`, `continue`, or `break` taken before a routine's primary path. Each one is either an assertion of a precondition or carries a comment proving the case arises and is handled correctly.
_Avoid_: bail-out, guard (for the statement itself)

**Workaround (WAR)**:
Code that handles a symptom at a consumer instead of fixing its producer, such as a null check for a shape that should never arise. Reviewers call it a WAR or band-aid; it needs a filed bug and a justifying comment to be accepted.

**Predicate**:
A named Boolean helper that states exactly the condition it tests. Any condition with three or more `&&` or `||` operators becomes one, as a form of documentation.

**Bottleneck**:
The single routine through which every instance of a check or policy flows. A predicate written twice or a copy-pasted sequence is refactored into one bottleneck.
