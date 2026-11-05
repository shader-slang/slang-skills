# slang-rhi

The C++ render hardware interface that runs Slang programs on D3D11, D3D12, Vulkan, Metal, CUDA, WebGPU, and CPU. Its nouns cover devices, resources, shader binding, pipelines, and command recording.

## Devices

**Device**:
`IDevice`: the root object for one GPU or CPU backend instance. It creates every other object and owns their lifetime.

**Device type**:
`DeviceType`: the enum naming which backend a device uses: `D3D11`, `D3D12`, `Vulkan`, `Metal`, `CUDA`, `WGPU`, or `CPU`.
_Avoid_: backend (when the enum value is meant)

**Backend**:
One per-API implementation of the RHI interfaces under `src/`. In slang-rhi this word names the implementation layer, not a Slang compilation target.

## Shader binding

**Shader program**:
`IShaderProgram`: the linked Slang component types for one program, created from a global scope and entry points with a `LinkingStyle`.

**Shader object**:
`IShaderObject`: the typed container that holds argument values and resource bindings for one Slang parameter scope, mirroring the program's reflected layout.
_Avoid_: descriptor set (when the RHI object is meant)

**Shader offset**:
`ShaderOffset`: a position inside a shader object as a uniform byte offset plus a binding-range index and array index. A shader cursor navigates these offsets by field name.

**Descriptor handle**:
`DescriptorHandle`: a device-wide index for a resource view or sampler used by bindless shaders. It is obtained from the resource and written into a shader object as plain data.

**Synthetic resource binding**:
A binding for a compiler-synthesized resource absent from normal reflection, such as a coverage counter buffer, declared with `ShaderProgramSyntheticResourcesDesc`.

## Resources and memory

**Resource**:
`IResource`: a buffer, texture, texture view, sampler, acceleration structure, or micromap owned by a device.

**Resource state**:
`ResourceState`: the usage a resource is in at a point in a command stream, such as `ShaderResource` or `UnorderedAccess`, declared through barriers.

**Heap**:
`IHeap`: a general allocator for device memory, including the device's staging heap for uploads and downloads.
_Avoid_: resource heap (for `IHeap`)

**Resource heap**:
`IResourceHeap`: memory in which resources are placed at an offset instead of being committed. Overlapping resources alias and are activated with `aliasResources`.
_Avoid_: heap (bare, when placement is meant)

**Surface**:
`ISurface`: the presentable images of a window, configured with `SurfaceConfig`.
_Avoid_: swapchain, swap chain

## Commands and pipelines

**Command encoder**:
`ICommandEncoder`: the recorder of GPU work that finishes into a command buffer. It opens render, compute, and ray-tracing pass encoders in which a pipeline is bound.
_Avoid_: command list

**Command buffer**:
`ICommandBuffer`: finished recorded work submitted to a command queue with `SubmitDesc`; a fence signals completion.
_Avoid_: command list

**Pipeline**:
`IPipeline` and its render, compute, and ray-tracing subtypes: a compiled shader program plus fixed-function state, ready to bind in a pass encoder.
_Avoid_: pipeline state

**Internal reference**:
`InternalRefPtr`: an owning reference that retains an object but not its device, used for device-internal edges. An external reference, `ComPtr` or `RefPtr`, retains both.
_Avoid_: weak reference (for `InternalRefPtr`)
