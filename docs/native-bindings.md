# Native bindings

ContextLease uses one Rust implementation and a versioned C ABI. Build the native core first:

```bash
cargo build -p contextlease-ffi --release
```

Artifacts are written to `target/release`:

- Windows: `contextlease_native.dll` plus import/static libraries
- Linux: `libcontextlease_native.so` and `libcontextlease_native.a`
- macOS: `libcontextlease_native.dylib` and `libcontextlease_native.a`

The ABI version is currently `1`. Every binding checks it before creating an arena.

## C and C++

Include `bindings/c/include/contextlease.h`. C++ applications can instead include
`bindings/cpp/include/contextlease.hpp` for RAII ownership. Link the import/shared library
for the target platform and place the runtime library beside the executable or on the
platform library search path.

## Python

Set `CONTEXTLEASE_NATIVE_LIBRARY` to the absolute shared-library path, or place the library
at `contextlease/native/<platform-library-name>` inside the installed package.

```python
from contextlease import NativeArena

with NativeArena(definition) as arena:
    result = arena.prepare(request)
```

## .NET and Unity

Build `bindings/dotnet/src/ContextLease.Managed/ContextLease.Managed.csproj`. The package
targets `netstandard2.0` and `net471`. Put the managed assembly on the application reference
path and the native library on its native search path.

The managed binding uses the ABI- and release-qualified native name `contextlease_native_abi1_v0_2_0` so a new
ABI-compatible build can be deployed beside an older DLL that is still loaded by Unity.
For Unity on Windows:

```text
Assets/Plugins/ContextLease/ContextLease.Managed.dll
Assets/Plugins/x86_64/contextlease_native_abi1_v0_2_0.dll
```

## Go

The cgo package expects the native library under one of these folders:

```text
bindings/go/native/windows-x86_64
bindings/go/native/linux-x86_64
bindings/go/native/macos-universal
```

The shared library must also be discoverable at runtime through `PATH`, `LD_LIBRARY_PATH`,
or `DYLD_LIBRARY_PATH`, respectively.

## Ownership rules

- `cl_arena_create` returns an arena owned by the caller; release it with `cl_arena_free`.
- `cl_arena_prepare` and `cl_core_version` return strings owned by the caller; release them
  with `cl_string_free`.
- `cl_last_error` returns thread-local borrowed memory; never free it.
- The ABI catches Rust panics and reports an error code plus JSON error detail.

## Two-phase semantic providers

Call `cl_arena_prepare_begin`. A `ready` response already contains `prepared`; a
`needs_semantic` response contains one or more requests with provider id, source text,
target tokens, required terms, and an opaque `semantic_request_id`. Invoke those providers
in the host process, then pass an array of `{semantic_request_id, content}` objects to
`cl_arena_prepare_commit` together with the unchanged original request JSON. The commit
rejects duplicate, unexpected, missing, growing, or required-term-losing candidates.
