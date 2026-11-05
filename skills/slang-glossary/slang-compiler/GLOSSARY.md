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

**Emitter**:
The per-target code in `slang-emit-*.cpp` that turns legalized IR into HLSL, GLSL, SPIR-V, Metal, WGSL, CUDA, or C++ output.
_Avoid_: backend (when the emitter code is meant), back-end

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

**Borrow-in parameter**:
A parameter passed as a reference to an immutable borrowed value, `ParamPassingMode::BorrowIn`. It is spelled `__constref` in source and printed as `borrow T`.
_Avoid_: ConstRef, const ref, constref

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

## API objects and layout

**Session**:
The public `ISession`: a scope holding loaded modules, search paths, and targets. Its C++ class is `Linkage`; the coarser `IGlobalSession` owns the core module and downstream-compiler discovery.
_Avoid_: linkage (in API-facing prose)

**Component type**:
A unit of composition, `IComponentType`: a module, an entry point, a type conformance, or a composite of these. Linking a composite yields the program whose kernels are requested.

**Type layout**:
The target-dependent description of how much of each layout unit a type consumes and where its fields and elements sit.

**Layout unit**:
One kind of resource a parameter can consume, such as bytes, `t` registers, or descriptor-table slots. The API enum is `ParameterCategory`.
_Avoid_: parameter category (in prose)

**Parameter binding**:
The per-target step that assigns registers, bindings, and byte offsets to every shader parameter of a composed program, honoring explicit `register` and `[[vk::binding]]` markup first.
