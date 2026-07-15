# Architecture

ContextLease is a prompt-resource control plane. The host application owns prompt semantics and supplies modules; the framework manages the shared token budget.

## Ownership boundary

| Host application | ContextLease |
|---|---|
| Defines modules and their meaning | Validates floor, target, maximum, and reclaim rules |
| Supplies fixed and variable chunks | Counts demand and allocates capacity |
| Chooses model/context profile | Grants and recalculates revocable leases |
| Configures provider credentials by env name | Runs deterministic and semantic compression |
| Sends the final request to the model | Produces prepared context and content-free telemetry |

There is no AINPC-, RAG-, or agent-framework-specific module in the core package.

## Arena lifecycle

1. `compile_layout()` freezes and hashes the externally supplied arena definition.
2. `prepare()` validates the model budget and measures current module demand.
3. The allocator satisfies demand through floor, target, and expansion phases.
4. Capacity above a borrower's local target becomes a donor-attributed lease.
5. If the borrower exceeds its current allocation, its registered pipeline reclaims elastic content.
6. The renderer composes modules in stable order and verifies the final token bound.
7. A bounded observation store publishes a snapshot and trace events.

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
protected floor → local target → borrowed expansion → unused slack
```

Targets are demand-capped. A module with no current demand does not reserve its whole target, so that capacity can be lent. Floors remain the admission/protection contract for non-empty modules.

## Lease identity and reclaim

A lease records donor, borrower, granted tokens, current use, reclaimability, and the borrower's release pipeline. Leases are recalculated from current demand on each request. When donor demand grows, the previous grant shrinks and a `lease.reclaimed` event is emitted.

No background thread mutates prompt content. Reclamation is deterministic within the next `prepare()` transaction, which keeps prepared contexts immutable and request-local.

## Compression contracts

Algorithms implement a small protocol: receive content, target tokens, token counter, options, services, required terms, and metadata; return content plus trace data. The pipeline enforces:

- output does not grow;
- target is met before the request is admitted;
- required terms survive;
- failures can fall through to later registered steps;
- pinned content never enters the elastic pipeline.

Semantic algorithms resolve providers by ID from `SummaryProviderRegistry`; no provider global state is required.

## Observation and privacy

The observation store is a bounded in-memory ring. Events contain counts, IDs, policies, hashes, selected provider/model, and algorithm trace—but never prompt bodies. The Debug Web consumes the same public DTOs exposed through REST and SSE.

## Extension points

- `TokenCounter` for model-specific exact tokenizers.
- `CompressionAlgorithm` for domain-aware reduction.
- `SummaryProvider` for custom inference gateways.
- Host-side serialization for message arrays or tool schemas.
- External trace export by subscribing to `ObservationStore` data.
