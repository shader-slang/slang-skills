# Slang Language

What a shader author sees when writing and compiling Slang: language constructs, the shader execution model, and the compilation model. The user guide and the formal specification are the sources; the specification wins where they differ.

## Program structure and modules

**Module**:
One or more files compiled together, named by a `module` declaration in its primary file and extended with `__include` of files that declare `implementing`. Other code brings a module in with `import`.

**Precompiled module**:
A module serialized to a `.slang-module` file after front-end compilation and linked later with link-time constants or types.
_Avoid_: binary module, IR module (in user-facing text)

**Link-time constant**:
An `extern static const` whose value another module supplies with `export` when the modules are linked, so specialization happens after precompilation.
_Avoid_: specialization constant (that term names the Vulkan feature)

**Translation-time constant**:
A value the toolchain fixes before the program runs: a compile-time constant, a link-time constant, or a codegen constant. The specification prefers this term over the looser "compile-time constant".
_Avoid_: compile-time constant (for the whole class)

**Language version**:
The Slang language revision a module is compiled under, such as 2025 or 202c, selected by a `#language slang <year>` declaration or a compiler option. Tests about version-dependent behavior pin it explicitly; warnings may become errors in a later version.
_Avoid_: module version, dialect (for the version)

## Entry points and execution

**Entry point**:
A function marked `[shader("...")]` for a pipeline stage, from which a thread begins execution. One entry point can be compiled into many kernels.
_Avoid_: kernel (except in CUDA text), main function

**Kernel**:
The compiled code for one entry point on one target and composition. The specification also calls a compute-stage entry point a compute kernel.

**Shader parameter**:
A global or entry-point `uniform` input that the host application supplies outside pipeline dataflow, such as `ConstantBuffer<T> c;` or `Texture2D t;`.

**Entry-point uniform parameter**:
A `uniform` parameter of an entry-point function, laid out like a global shader parameter but scoped to that entry point.
_Avoid_: kernel parameter, launch parameter

**Binding semantic**:
The `: NAME` suffix on a varying entry-point parameter or result that connects it to the system or an adjacent stage, such as `SV_DispatchThreadID`.
_Avoid_: semantic (bare)

**Parameter-passing mode**:
The `in`, `out`, or `inout` qualifier on a function parameter. The specification defines copy-in, copy-out, and copy-in-copy-out semantics; `__ref` and `__constref` are compiler spellings without a specification entry.
_Avoid_: parameter direction, passing convention

**Readonly ref access**:
The `readonly` qualifier on a `ref` parameter, giving the callee read-only access to the caller's storage; `writeonly` is its counterpart. `const` in that position is a legacy alias and wrongly suggests the data itself is constant.
_Avoid_: const (as the ref access qualifier)

**Thread**:
A sequential stream of executed instructions that starts at an entry-point invocation. The specification distinguishes the invocation, one unit of work, from the thread that executes it.
_Avoid_: invocation (when the executing thread is meant)

**Wave**:
The smallest group of threads in the execution hierarchy, 4 to 128 threads defined by the target, executing in SIMT fashion and sharing wave-tangled functions.
_Avoid_: subgroup

**Thread group**:
The group of compute threads that shares `groupshared` memory and group barriers. Its size comes from `[numthreads]` or dispatch parameters.
_Avoid_: workgroup, work group

**Dispatch**:
One compute workload: a 3-D grid of thread groups submitted by the application. Graphics work is a launch, which the pipeline divides into invocations.
_Avoid_: launch (for compute work)

**Dynamic uniform**:
A value guaranteed equal across all threads of a batch, marked with the `dynamic_uniform` modifier so uniformity analysis can check its uses.

## Shader parameters and layout

**Parameter block**:
`ParameterBlock<T>`: a Slang type that groups shader parameters so they bind as one unit, typically one descriptor set, register space, or argument buffer.
_Avoid_: descriptor set, constant buffer (when the Slang construct is meant)

**Space**:
The extra binding dimension a layout unit may have on a target: a Vulkan descriptor set, a D3D12 register space, or a WebGPU bind group.
_Avoid_: descriptor set, register space (when the target-neutral concept is meant)

**Profile**:
A named feature level for a target, such as `sm_6_6` or `glsl_460`, passed with `-profile` and expanded to capability atoms.

**Capability requirement**:
The set of capability atoms a declaration needs, declared with `[require(...)]` or inferred from its body, and checked against each target.
_Avoid_: capability (when the requirement on a declaration is meant)

## Types, interfaces, and generics

**Conformance**:
The relation "type `T` conforms to interface `I`", declared with `struct T : I` or an extension, and satisfied by members that implement each requirement.
_Avoid_: implements an interface

**Requirement**:
A member an interface demands of conforming types: a method, property, initializer, static constant, or associated type.

**Associated type**:
A type-valued requirement, `associatedtype`, that each conforming type supplies, so an interface can name types that differ per implementation.

**This type**:
The type `This`: the enclosing type, or in an interface the concrete conforming type.

**Generic**:
A declaration with type or value parameters in angle brackets, checked once against its constraints and specialized at each use. Constraints come from `T : I` or a `where` clause.
_Avoid_: template

**Extension**:
A declaration that adds members or conformances to an existing type without changing its layout.

**Existential box**:
A value of an interface used as a proper type, written `dyn IFoo` in language version 202c; the interface itself is only the contract. It packs a concrete value with its conformance, so calls through it dispatch dynamically.
_Avoid_: interface-typed value, interface variant (the specification's experimental term), existential value

## Expressions, statements, and errors

**Operator**:
A prefix, postfix, or infix operator that can appear in an operator expression, such as `+`, `!`, or `++`. Names written with `operator` syntax that cannot appear there, such as `operator=`, are not operators.

**Tuple construction**:
The expression `(a, b)` that builds a tuple from comma-separated values, the meaning a parenthesized comma list has in Slang 2026 and later. The language reference notes this beside the earlier reading of the same spelling.

**Error**:
A value of an error type that a function declared `throws` raises with `throw`, and a caller handles with `try` and `catch`. Prose says error and raise; "exception" names a different mechanism Slang does not have.
_Avoid_: exception, throw an exception (in prose)

## Automatic differentiation

**Derivative function**:
The function `fwd_diff(f)` or `bwd_diff(f)` that the compiler synthesizes from a `[Differentiable]` function `f`, or a user-written one named by `[ForwardDerivative]` or `[BackwardDerivative]`.

**Differential pair**:
`DifferentialPair<T>`: a primal value of type `T` paired with its differential of type `T.Differential`, passed to and from derivative functions.
