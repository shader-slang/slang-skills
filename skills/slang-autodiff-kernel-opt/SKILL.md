---
name: slang-autodiff-kernel-opt
description: >-
  Optimize Slang autodiff backward kernel performance by analyzing register
  pressure, checkpoint storage, and spills. Use when investigating slow
  backward kernels, removing custom [BackwardDerivativeOf] functions, or
  reducing register pressure in differentiable GPU code, including tuning
  [ForceUnroll] versus [MaxIters] loop behavior per call site.
---

# Autodiff Kernel Optimization

Methodology for investigating and optimizing Slang autodiff backward kernel
performance.

## Investigation workflow

### 1. Isolation

Large projects have complex build systems (Bazel, CMake) with many dependencies.
For kernel investigation, extract the target function into a self-contained
`.slang` file that compiles directly with `slangc`. This cuts the edit-compile
cycle from minutes to seconds.

**Guidelines:**
- Identify the target kernel — the one with the worst backward performance or
  highest register count.
- Create a new `.slang` file containing only the code needed for that kernel.
  Inline small dependencies; `#include` larger shared ones.
- If the original code uses a module system (`import`), avoid it — standalone
  compilation via `#include` is more reliable and avoids module deserialization
  issues.
- Use `#ifdef` guards for A/B variant testing from the same source file:

```slang
#ifndef USE_AUTODIFF
[BackwardDerivativeOf(my_func)]
void my_func_bwd(...) { /* custom backward */ }
#endif
```

Compile with/without `-DUSE_AUTODIFF` to compare.

- For fully portable benchmarks, inline all dependencies so the file compiles
  with zero `-I` flags. This makes the experiment shareable as a standalone
  package.

**CUDA example:**

```bash
# slangc generates a self-contained .cu (includes Slang CUDA prelude)
slangc my_shader.slang -O3 -target cuda -o /tmp/out.cu

# nvcc compiles with register/spill reporting
nvcc /tmp/out.cu -arch=sm_89 --use_fast_math \
  -D__CUDA_NO_HALF_OPERATORS__ -D__CUDA_NO_HALF_CONVERSIONS__ \
  -D__CUDA_NO_BFLOAT16_CONVERSIONS__ -D__CUDA_NO_HALF2_OPERATORS__ \
  --ptxas-options=-v -cubin -o /tmp/out.cubin 2>&1 | grep -A2 "_bwd_diff$"
```

The `-target cuda` output is self-contained — TensorView/DiffTensorView become
plain C++ structs. No PyTorch or slangtorch needed.

### 2. Register/spill analysis

Compile the isolated kernel to the target backend and check resource usage for
the `_bwd_diff` entry points.

| Field | Red flag |
|-------|----------|
| Registers | > 200 concerning, 255 = hardware cap (GPU) |
| Spill stores/loads | Any nonzero = performance killer |
| Stack frame | Large = deep non-inlined call chains |

### 3. Checkpoint analysis

Use `-report-checkpoint-intermediates` with any target to see what autodiff
stores in the forward pass for use in the backward pass:

```bash
slangc my_shader.slang -O3 -target cuda -report-checkpoint-intermediates -o /dev/null
```

**Example.** Given this kernel:

```slang
uint2 get_index<let N : int>(no_diff uint index) {
    return uint2(index / N, index - (index / N) * N);
}

[CUDAKernel] [Differentiable] [AutoPyBindCUDA]
void loop_kernel(no_diff uint count, DiffTensorView output, DiffTensorView input) {
    uint tid = cudaBlockIdx().x * cudaBlockDim().x + cudaThreadIdx().x;
    if (tid >= count) return;
    [ForceUnroll]
    for (int i = 0; i < 8; ++i) {
        uint2 index = get_index<8>(i * count + tid);
        float x = input.loadOnce(index);
        output.storeOnce(index, square(x));
    }
}
```

The report shows:

```
note: checkpointing context of 96 bytes associated with: 'loop_kernel'
  --> example.slang:6:6
   |
 6 | void loop_kernel(...)
   |      ^^^^^^^^^^^
...
13 |         uint2 index = get_index<8>(i * count + tid);
   |                                   - 8 instances of 8 bytes (Vector<uint32_t, 2>)
14 |         float x = input.loadOnce(index);
   |                                 - 8 instances of 4 bytes (float)
---'
```

Two variables are stored per unrolled iteration: `index` (uint2, 8 bytes) and
`x` (float, 4 bytes), for 8 iterations = 96 bytes total. Note that `index` is
computed purely from `no_diff` values and shouldn't need checkpointing — this
is a candidate for `[PreferRecompute]` (see Strategy 1 below).

For `[MaxIters(N)]` loops, storage appears as `FixedArray<T, N+2>` instead of
`N instances of`.

**What to look for:**
- **Large per-iteration storage**: many instances of a variable in an unrolled
  loop. The total bytes = instances x size_per_instance. This is the main
  source of register pressure.
- **Redundant storage**: values recomputable from already-stored values.
- **Non-diff values being stored**: computations derived entirely from
  `no_diff` inputs that shouldn't need checkpointing. These are candidates
  for `[PreferRecompute]`.
- **Tasks with zero checkpoint**: functions with
  `[BackwardDerivativeOf]` show no checkpoint. When comparing, this tells
  you the cost that autodiff would add if the custom backward were removed.

### 4. Benchmarking

Register counts and checkpoint analysis predict performance but don't prove it.
Always measure actual runtime to confirm improvements.

**Guidelines:**
- Compile both the original and optimized variants from the same source
  (using `#ifdef` toggles).
- Use the target platform's profiling/timing mechanism.
- Run warmup iterations before measurement to stabilize caches and clocks.
- Run multiple times and average to reduce noise.

**CUDA example:** Write a host launcher that `#include`s the slangc-generated
`.cu`, allocates GPU tensors, and times kernel launches with `cudaEvent_t`.

## Optimization strategies

### Strategy 1: `[PreferRecompute]` on pure/cheap functions

If a function's output is checkpointed per iteration but can be recomputed
cheaply, mark it `[PreferRecompute]`. Two proven patterns:

**Pattern A: Pure functions of no_diff inputs.** If a function's inputs are
all `no_diff` (loop counters, thread IDs, constants), its output is free to
recompute. Mark it `[PreferRecompute]` to avoid checkpointing the return value
per iteration.

```slang
// Before: autodiff stores the returned uint2 per iteration
uint2 computeCoord(no_diff uint flatIndex) { ... }

// After: backward recomputes it instead of storing
[PreferRecompute]
uint2 computeCoord(no_diff uint flatIndex) { ... }
```

If the function has side effects (e.g., tensor loads via `loadOnce`), use
`[PreferRecompute(SideEffectBehavior::Allow)]` to suppress the warning that
recomputing may re-execute side effects. This is safe when the side effect is
an idempotent read.

**Pattern B: Cheap-to-redo work.** If a value can be reproduced by re-reading
memory or re-running a trivial computation, wrap that work in a
`[PreferRecompute]` helper. This trades re-execution in the backward pass for
fewer bytes of checkpoint storage. Good when the re-execution cost (e.g., one
global memory load) is cheaper than the register pressure from storing the
value across many iterations.

```slang
// Before: autodiff stores val (4 bytes) per iteration
for (int i = 0; i < N; ++i) {
    float val = input.load(index);
    float newVal = operationsOn(val);
    output.store(index, newVal);
}

// After: wrap load+operations so backward re-reads from memory
[PreferRecompute]
[Differentiable]
float loadAndCompute(DiffTensorView input, uint2 index) {
    return operationsOn(input.load(index));
}

for (int i = 0; i < N; ++i) {
    output.store(index, loadAndCompute(input, index));
}
```

### Strategy 2: `[MaxIters(N)]` instead of `[ForceUnroll]`

When a `[ForceUnroll]` loop stores checkpoint context per iteration, switching
to `[MaxIters(N)]` makes autodiff use loop replay with compact FixedArray
storage instead of N separate SSA values. Best for large N (e.g., 48-iteration
copy loops). Not beneficial when per-iteration state is small enough to fit in
registers without spilling.

| Scenario | Prefer |
|----------|--------|
| Large N, causes spills with ForceUnroll | `[MaxIters(N)]` |
| Small N, no spills | `[ForceUnroll]` |
| N varies across specializations | Profile both |

**Per-call threshold pattern.** If a shared differentiable helper is not easy
to switch globally to `[MaxIters]`, add a generic threshold parameter and choose
the loop annotation from compile-time constants. This lets each task or kernel
specialization opt into loop replay only where profiling proves it helps.

```slang
[Differentiable]
void visitComponents<let ComponentCount : int, let ReplayThreshold : int>(
    no_diff uint elementId)
{
    if (ComponentCount > ReplayThreshold) {
        [MaxIters(ComponentCount)]
        for (int componentId = 0; componentId < ComponentCount; ++componentId) {
            // Call the target differentiable function here.
        }
    }
    else {
        [ForceUnroll]
        for (int componentId = 0; componentId < ComponentCount; ++componentId) {
            // Call the target differentiable function here.
        }
    }
}

// Keep small or sensitive call sites unrolled.
visitComponents<20, 1024>(elementId);

// Replay only the specialization where 45 iterations reduced register pressure.
visitComponents<45, 44>(elementId);
```

Use this pattern when:
- A global `[MaxIters]` change improves one kernel but regresses another.
- The same helper is instantiated by multiple tasks with different register
  pressure, occupancy, or checkpoint behavior.
- You need to preserve manual-backward parity for some call sites while
  improving a large-loop specialization.

Benchmark each threshold candidate. In practice, a threshold just below the
problematic loop trip count, such as `44` for a 45-element copy, can isolate the
benefit while leaving other specializations on the original unrolled path.

### Strategy 3: Eliminate redundant loop-carried variables

If a loop-carried variable is only used in a non-differentiable context
(e.g., convergence checks, early termination), it doesn't need gradients.
Use `detach()` to prevent autodiff from tracking it:

```slang
// Before: prev_point is a loop phi — stored per iteration for autodiff
float2 prev_point = float2(0, 0);
for (...) {
    float2 pixel_diff = result.point - prev_point;  // used for convergence check
    if (length(pixel_diff) < threshold) break;
    prev_point = result.point;
}

// After: detach() tells autodiff this value doesn't need gradients
for (...) {
    float2 prev = detach(result.point);
    float2 pixel_diff = detach(result.point) - prev;
    if (length(pixel_diff) < threshold) break;
}
```

Only use `detach()` when the variable genuinely doesn't need derivatives.
If `prev_point` participates in differentiable computation (not just control
flow), detaching it will produce incorrect gradients.

### Strategy 4: Split phases (convergence loop + single diff step)

For iterative convergence loops. Extract the loop into a non-`[Differentiable]`
solver, call via `no_diff`, then do one differentiable step:

```slang
ConvergenceResult _solve(...) { /* plain loop, not [Differentiable] */ }

[Differentiable]
Result my_func(...) {
    ConvergenceResult cr = no_diff _solve(...);
    return differentiable_step(cr.converged_params, ...);
}
```

Eliminates ALL loop checkpoint storage. Produces code equivalent to a
hand-written `[BackwardDerivativeOf]` without writing the backward manually.

### Strategy 5: Custom derivatives with `[BackwardDerivativeOf]`

As a last resort, write a manual backward when autodiff fundamentally cannot
derive the correct result:

- **Different math**: the backward requires a mathematically different
  formulation (e.g., implicit differentiation, adjoint methods) that cannot
  be expressed by mechanically differentiating the forward code.
- **Synchronization / memory access patterns**: the backward needs warp-level
  reductions (`WaveActiveSum`), shared memory atomics, or other coordination
  that autodiff doesn't generate.

```slang
[BackwardDerivativeOf(my_func)]
void my_func_bwd(...) { /* hand-written backward */ }
```

**Use this minimally.** Custom derivatives duplicate logic (forward and backward
must stay in sync), increase code size, and bypass the compiler's checkpoint
optimizations. Prefer Strategies 1-4 first — they let autodiff generate
correct derivatives while controlling performance via annotations. Only fall
back to `[BackwardDerivativeOf]` when the backward truly requires different
logic that autodiff cannot produce.
