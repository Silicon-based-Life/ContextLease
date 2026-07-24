# Architecture

ContextLease is a prompt-resource control plane. The host owns prompt semantics and supplies modules; the framework manages the shared token budget. There is no host-application-specific module in the core package.

## Ownership boundary

| Host application | ContextLease Rust kernel |
|---|---|
| Defines modules and their meaning | Validates floor, target, maximum, and reclaim rules |
| Supplies fixed and variable chunks | Counts demand and allocates capacity |
| Chooses model/context profile and exact tokenizer | Grants and recalculates revocable leases |
| Configures provider credentials by env name | Runs deterministic compression and validates semantic results |
| Renders provider-specific messages/tools and sends the request | Produces structured plans and content-free telemetry |

Python, C, C++, Go, C#, Unity, and direct Rust consumers all reach this same kernel. Language wrappers adapt DTOs and callbacks; they do not implement allocation or reclaim behavior.

## Arena lifecycle

1. The Rust kernel validates, freezes, and hashes the externally supplied arena definition.
2. `prepare(ContextPlan)` validates the model budget and measures current module demand.
3. The allocator satisfies demand through floor, target, and expansion phases.
4. Capacity above a borrower's local target becomes a donor-attributed lease.
5. If the borrower exceeds its current allocation, its registered pipeline reclaims elastic content.
6. The kernel returns a structured `PreparedContextPlan`; its compatibility renderer composes stable text and verifies the final token bound.
7. The native arena commits a content-free snapshot and bounded trace-event ring in the same transaction.

## Allocation model

For model profile `m` and arena `a`:

```text
usable_input = m.context_limit
             - m.reserved_output
             - a.framework_reserve
             - render_overhead
```

The allocator then applies:

```text
protected floor -> local target -> borrowed expansion -> unused slack
```

Targets are demand-capped. A module with no current demand does not reserve its whole target, so that capacity can be lent. Floors remain the admission/protection contract for non-empty modules.

## Lease identity and reclaim

A lease records donor, borrower, granted tokens, current use, reclaimability, and the borrower's release pipeline. Leases are recalculated from current demand on each request. When donor demand grows, the previous grant shrinks and a `lease.reclaimed` event is emitted.

No background thread mutates prompt content. Reclamation is deterministic within the next `prepare()` transaction, which keeps prepared contexts immutable and request-local.

## Token counting and calibration

ABI v2 accepts a synchronous host tokenizer callback. `exact` requires it; `hybrid` can use it; estimated counts use the deterministic built-in estimator. Provider-reported `{request_id, actual_input_tokens}` observations update a conservative EWMA safety multiplier keyed by model profile, tokenizer ID, and tokenizer version.

## Compression contracts

Canonical Rust algorithms receive content, target tokens, tokenizer, options, required terms, and metadata. Semantic steps emit a two-phase host request. The kernel enforces:

- output does not grow;
- target is met before admission;
- required terms survive;
- failures can fall through to later registered steps;
- pinned content never enters the elastic pipeline.

Semantic requests resolve providers by ID in the host's `SummaryProviderRegistry`; credentials and network clients never enter the kernel.

## Structured output

`PreparedContextPlan` retains module identity, render target, allocation, usage, chunks, compression provenance, snapshot, and request events. Hosts can render messages, tool schemas, or custom structures without reconstructing them from a flattened string. `rendered` remains a compatibility convenience.

## Observation and privacy

The native arena owns the bounded event ring and latest snapshot. Events contain counts, IDs, policies, and hashes, but never prompt bodies. Python's `ObservationStore` mirrors these native DTOs for REST/SSE and Debug Web presentation; it is not an independent source of runtime truth.

## Extension points

- ABI v2 token callback for model-specific exact tokenizers.
- Rust compression algorithms or host-side pre-processing for domain-aware reduction.
- `SummaryProvider` for custom inference gateways.
- Host-side render adapters over structured module/chunk plans.
- External trace export through native snapshot/event pull APIs.
