# SlangPy

The Python library that calls Slang functions on the GPU by generating and dispatching compute kernels from Python arguments. Its nouns describe the call from Python, not the shader itself.

## Loading and calling

**Module**:
`spy.Module`: a loaded Slang module whose global functions and structs are reached as attributes, such as `module.add`.

**Function**:
`spy.Function`: a callable wrapper around a Slang function. It generates, caches, and dispatches a kernel the first time it is called with a given argument signature; `map`, `bwds`, and `set` return modified function objects.

**Struct**:
`spy.Struct`: a Slang struct reached through a module, whose constructor and methods can be called on tensors of instances.

**Vectorized call**:
A call that applies a scalar Slang function to whole containers; SlangPy infers one thread per element from the argument shapes. A call with only scalar arguments runs once.
_Avoid_: kernel launch

**Broadcasting**:
The rules that reconcile argument shapes dimension by dimension: equal sizes match, size 1 expands, and a scalar expands to every dimension. `strict_broadcasting` disables automatic dimension padding.

**Dimensionality**:
The number of dimensions of a value after the Slang parameter's own dimensions are subtracted. A `float3` has dimensionality 1 and shape `(3,)`.

**Call shape**:
The shape of the whole dispatch, computed from the broadcast argument shapes; one thread runs per element. A thread's position in it is its call id.

**Call group**:
A rectangular tile of the call shape set with `call_group_shape`, executed as one GPU thread group. `CallShapeInfo` exposes the call id, group id, and position within the group.

**Mapping**:
`Function.map`: an explicit statement of which argument dimensions feed which call-shape dimensions, or which Slang type a Python value takes.

**Generator**:
An argument such as `call_id()`, `thread_id()`, `grid()`, `rand_float()`, or `wang_hash()` whose values the kernel computes per thread instead of reading from memory.

**Raw dispatch**:
`Function.dispatch`: running a Slang function as a compute entry point with an explicit thread count, bypassing vectorization and code generation. `_thread_count` serves `[CUDAKernel]` functions the same way.
_Avoid_: launch

**Return type**:
The container SlangPy allocates for a result, chosen with `_result`: `'numpy'`, `'texture'`, `'tensor'`, a type, or an existing object to fill.

## Data

**Tensor**:
`spy.Tensor`: the single N-dimensional container, with a Slang element type, shape, strides, and optional gradient storage. In Slang it appears as `Tensor`, `RWTensor`, `DiffTensor`, and related types.
_Avoid_: NDBuffer, TensorView, DiffTensorView

**InstanceList**:
A list of Slang struct instances stored field by field in separate tensors, on which struct methods are called. `InstanceTensor` is the single-tensor form.

**DiffPair**:
`spy.DiffPair`: a primal value paired with its gradient, used to pass and receive derivatives for scalar arguments.

**Backward call**:
`Function.bwds`: a function object that runs `bwd_diff` of the Slang function, reading result gradients and accumulating argument gradients. Gradients always accumulate, so gradient buffers must be zeroed first.

**Coordinate convention**:
Array coordinates index like NumPy, with the rightmost dimension fastest; vector coordinates follow graphics, with `x` fastest. The same tensor position has different coordinates in each.

## Generation internals

**Marshall**:
The per-type object that describes how a Python value is passed to and from a generated kernel. It supplies the Slang type, load and store code, and binding.

**Prelude (SlangPy)**:
`Function.prelude`: raw Slang source injected into the generated kernel module. It is unrelated to the Slang compiler's target prelude headers.
