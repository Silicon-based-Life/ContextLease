# ContextLease Roadmap

ContextLease is an alpha project. This roadmap describes intended direction, not
a compatibility promise. Scope is deliberately constrained: the project should
remain a small, embeddable context allocator rather than become a distributed
agent platform.

## 0.3 — Public alpha foundation

- One canonical Rust behavior kernel behind ABI v2.
- Cross-language bindings for Python, C, C++, Go, and .NET/Unity.
- Structured prepare plans, two-phase semantic compression, exact-tokenizer
  callbacks, usage calibration, and content-free native telemetry.
- Shared conformance fixtures, platform wheel validation, RID-native NuGet
  packaging, native SDK archives, and public-project governance.

## 0.4 — Practical Context Scheduler

The scheduler work will extend the existing allocator without replacing it:

1. **Hierarchical scopes.** Add a `scope_path` such as
   `tenant/agent/session/turn/module/chunk`. Budgets are enforced at configured
   boundaries; the first implementation allocates only among siblings and
   avoids a general distributed quota service.
2. **Stable adaptive leases.** Add optional monotonic TTLs and two watermarks for
   reclaim hysteresis. Expiration and pressure remain deterministic under an
   injectable clock.
3. **Fairness under pressure.** Use weighted sibling fairness with bounded aging,
   plus priority-inversion protection for a high-priority requester blocked by
   lower-priority borrowed capacity.
4. **Atomic context groups.** An optional `atomic_group_id` keeps related chunks,
   especially tool call/result pairs, admitted, reclaimed, or rejected together.
5. **Pure simulation.** Shadow allocation, trace replay, and what-if analysis
   consume immutable inputs and produce plans without mutating the live arena.

Each item must first ship behind an explicit opt-in capability. Existing flat
arena behavior remains the compatibility baseline until the hierarchical
contract is proven by shared conformance fixtures.

## Quality gates

- Schema, Rust DTOs, FFI JSON, and language wrappers agree on every public field.
- Deterministic fixtures cover hierarchy, TTL expiry, hysteresis, fairness,
  priority inversion, and atomic groups.
- Replay of the same input and clock produces byte-equivalent prepared plans.
- Simulation never changes snapshots, events, calibration, or active leases.
- Complexity and hot-path allocation costs are measured before an API is made
  stable.

## Explicit non-goals for 0.4

- A distributed lease coordinator or consensus protocol.
- A general-purpose DAG/workflow scheduler.
- Learned allocation policies or online model training.
- A persistent trace warehouse.
- Authentication, tenancy provisioning, or billing.

## Toward 1.0

The `1.0` milestone requires a documented compatibility window, production usage
feedback from more than one host application, stable failure semantics, audited
unsafe/FFI boundaries, and repeatable release publication. See
[stability.md](stability.md) for the current compatibility policy.
