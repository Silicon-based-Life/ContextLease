from __future__ import annotations

import json
import threading
import uuid
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any, Iterable, Mapping

from .allocation import allocate_budget
from .compression import CompressionPipeline, CompressionRequest, CompressionRegistry, create_builtin_registry
from .enums import EventPriority, LeaseState, Pressure, ProtectionPolicy
from .errors import AdmissionError, ConfigurationError
from .layout import compile_layout, validate_model_budget
from .models import (
    ArenaDefinition,
    ArenaSnapshot,
    Lease,
    ModelProfile,
    ModuleAllocation,
    ModuleContribution,
    ModuleUsage,
    PreparedContext,
    PromptChunk,
    TraceEvent,
)
from .observation import ObservationStore
from .providers import SummaryProviderRegistry
from .tokenization import RegexTokenCounter, TokenCounter


def _pressure(used: int, capacity: int) -> Pressure:
    if capacity <= 0:
        return Pressure.OVERFLOW if used else Pressure.NORMAL
    ratio = used / capacity
    if ratio > 1:
        return Pressure.OVERFLOW
    if ratio >= 0.95:
        return Pressure.CRITICAL
    if ratio >= 0.8:
        return Pressure.ELEVATED
    return Pressure.NORMAL


def _render_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    return json.dumps(content, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


class ContextLeaseArena:
    def __init__(
        self,
        definition: ArenaDefinition,
        *,
        token_counter: TokenCounter | None = None,
        compression_registry: CompressionRegistry | None = None,
        summary_providers: SummaryProviderRegistry | None = None,
        observations: ObservationStore | None = None,
        instance_id: str | None = None,
    ) -> None:
        self.layout = compile_layout(definition)
        self.token_counter = token_counter or RegexTokenCounter()
        self.compression_registry = compression_registry or create_builtin_registry()
        self.compression_pipeline = CompressionPipeline(self.compression_registry)
        self.summary_providers = summary_providers or SummaryProviderRegistry()
        self.observations = observations or ObservationStore()
        self.instance_id = instance_id or uuid.uuid4().hex
        self._event_seq = 0
        self._snapshot_seq = 0
        self._active_leases: dict[str, Lease] = {}
        self._previous_usage: dict[str, int] = {}
        self._prepare_lock = threading.RLock()

    def _event(
        self,
        event_type: str,
        request_id: str | None,
        payload: Mapping[str, Any],
        priority: EventPriority = EventPriority.STATE,
    ) -> TraceEvent:
        self._event_seq += 1
        return TraceEvent(
            event_id=f"{self.instance_id}:{self._event_seq}",
            seq=self._event_seq,
            occurred_at=datetime.now(UTC),
            arena_id=self.layout.definition.arena_id,
            instance_id=self.instance_id,
            request_id=request_id,
            event_type=event_type,
            schema_version="1.0",
            layout_hash=self.layout.layout_hash,
            policy_version=self.layout.definition.policy_version,
            payload=payload,
            priority=priority,
        )

    def _validate_contributions(
        self, contributions: Iterable[ModuleContribution]
    ) -> dict[str, ModuleContribution]:
        result: dict[str, ModuleContribution] = {}
        for contribution in contributions:
            if contribution.module_id not in self.layout.module_by_id:
                raise ConfigurationError(f"unknown contribution module: {contribution.module_id}")
            if contribution.module_id in result:
                raise ConfigurationError(f"duplicate contribution module: {contribution.module_id}")
            chunk_ids: set[str] = set()
            for chunk in contribution.chunks:
                if chunk.chunk_id in chunk_ids:
                    raise ConfigurationError(
                        f"module {contribution.module_id} contains duplicate chunk_id {chunk.chunk_id}"
                    )
                chunk_ids.add(chunk.chunk_id)
            result[contribution.module_id] = contribution
        return result

    def _compress_module(
        self,
        module_id: str,
        chunks: tuple[PromptChunk, ...],
        allocation: ModuleAllocation,
    ) -> tuple[tuple[PromptChunk, ...], int, int, Mapping[str, Any]]:
        module = self.layout.module_by_id[module_id]
        pinned = tuple(
            chunk
            for chunk in chunks
            if module.protection == ProtectionPolicy.PINNED
            or chunk.protection == ProtectionPolicy.PINNED
        )
        elastic = tuple(chunk for chunk in chunks if chunk not in pinned)
        pinned_tokens = sum(self.token_counter.count_content(chunk.content) for chunk in pinned)
        before_tokens = sum(self.token_counter.count_content(chunk.content) for chunk in chunks)
        if pinned_tokens > allocation.allocated_tokens:
            raise AdmissionError(
                f"module {module_id}: pinned content needs {pinned_tokens} tokens, allocation is {allocation.allocated_tokens}"
            )
        elastic_target = allocation.allocated_tokens - pinned_tokens
        elastic_before = sum(self.token_counter.count_content(chunk.content) for chunk in elastic)
        if elastic_before <= elastic_target:
            return chunks, before_tokens, before_tokens, {"status": "not_needed"}
        if not module.reclaim_pipeline:
            raise AdmissionError(
                f"module {module_id}: over allocation and no reclaim pipeline is registered"
            )
        if not elastic:
            raise AdmissionError(f"module {module_id}: no elastic content is available for reclaim")

        if len(elastic) == 1:
            combined = elastic[0].content
            kind = elastic[0].kind
        elif all(isinstance(chunk.content, str) for chunk in elastic):
            combined = "\n\n".join(str(chunk.content) for chunk in elastic)
            kind = "text"
        else:
            combined = [
                {
                    "content": chunk.content,
                    "priority": chunk.priority,
                    "created_at": chunk.created_at.isoformat(),
                    "dependency_group": chunk.dependency_group,
                }
                for chunk in elastic
            ]
            kind = "collection"
        required_terms = tuple(dict.fromkeys(term for chunk in elastic for term in chunk.required_terms))
        result = self.compression_pipeline.execute(
            CompressionRequest(
                content=combined,
                target_tokens=elastic_target,
                counter=self.token_counter,
                required_terms=required_terms,
                services={"summary_providers": self.summary_providers},
                metadata={"arena_id": self.layout.definition.arena_id, "module_id": module_id},
            ),
            module.reclaim_pipeline,
            fail_open=True,
        )
        if result.after_tokens > elastic_target:
            raise AdmissionError(
                f"module {module_id}: reclaim pipeline left {result.after_tokens} elastic tokens, target is {elastic_target}"
            )
        compressed = PromptChunk(
            chunk_id=f"{module_id}:compressed",
            content=result.content,
            kind=kind,
            fixed=False,
            protection=ProtectionPolicy.ELASTIC,
            priority=max((chunk.priority for chunk in elastic), default=1.0),
            required_terms=required_terms,
            metadata={"compression_trace": result.trace, "source_chunks": len(elastic)},
        )
        final_chunks = pinned + (compressed,)
        after_tokens = sum(self.token_counter.count_content(chunk.content) for chunk in final_chunks)
        return final_chunks, before_tokens, after_tokens, result.trace

    def _lease_events(
        self, leases: tuple[Lease, ...], request_id: str
    ) -> list[TraceEvent]:
        events: list[TraceEvent] = []
        next_by_id = {lease.lease_id: lease for lease in leases}
        for lease_id, previous in self._active_leases.items():
            current = next_by_id.get(lease_id)
            reclaimed = previous.granted_tokens - (current.granted_tokens if current else 0)
            if reclaimed > 0:
                events.append(
                    self._event(
                        "lease.reclaimed",
                        request_id,
                        {
                            "lease_id": lease_id,
                            "donor_module_id": previous.donor_module_id,
                            "borrower_module_id": previous.borrower_module_id,
                            "reclaimed_tokens": reclaimed,
                            "release_pipeline": list(previous.release_pipeline),
                        },
                    )
                )
        for lease in leases:
            previous = self._active_leases.get(lease.lease_id)
            granted = lease.granted_tokens - (previous.granted_tokens if previous else 0)
            if granted > 0:
                events.append(
                    self._event(
                        "lease.granted",
                        request_id,
                        {
                            "lease_id": lease.lease_id,
                            "donor_module_id": lease.donor_module_id,
                            "borrower_module_id": lease.borrower_module_id,
                            "granted_tokens": granted,
                            "release_pipeline": list(lease.release_pipeline),
                        },
                    )
                )
        self._active_leases = next_by_id
        return events

    def prepare(
        self,
        model: ModelProfile,
        contributions: Iterable[ModuleContribution],
        *,
        request_id: str | None = None,
    ) -> PreparedContext:
        """Prepare one immutable context transaction.

        A single arena may be shared across request threads. Stateful lease,
        change-rate, snapshot, and trace updates are serialized per instance.
        """
        with self._prepare_lock:
            return self._prepare_locked(model, contributions, request_id=request_id)

    def _prepare_locked(
        self,
        model: ModelProfile,
        contributions: Iterable[ModuleContribution],
        *,
        request_id: str | None = None,
    ) -> PreparedContext:
        request_id = request_id or uuid.uuid4().hex
        validate_model_budget(self.layout, model.input_budget_tokens)
        contribution_by_id = self._validate_contributions(contributions)
        events = [
            self._event(
                "request.started",
                request_id,
                {"model_profile_id": model.model_profile_id, "token_count_mode": model.count_mode.value},
            )
        ]

        demands: dict[str, int] = {}
        original_chunks: dict[str, tuple[PromptChunk, ...]] = {}
        for module_id in self.layout.ordered_module_ids:
            contribution = contribution_by_id.get(module_id)
            chunks = contribution.chunks if contribution else ()
            original_chunks[module_id] = chunks
            calculated = sum(self.token_counter.count_content(chunk.content) for chunk in chunks)
            demands[module_id] = (
                contribution.observed_demand_tokens
                if contribution and contribution.observed_demand_tokens is not None
                else calculated
            )
            events.append(
                self._event(
                    "demand.observed",
                    request_id,
                    {"module_id": module_id, "demanded_tokens": demands[module_id]},
                    EventPriority.GAUGE,
                )
            )

        nonempty_module_count = sum(1 for demand in demands.values() if demand > 0)
        render_separator_tokens = self.token_counter.count_text(
            "\n\n" * max(0, nonempty_module_count - 1)
        )
        allocation_budget = model.input_budget_tokens - render_separator_tokens
        validate_model_budget(self.layout, allocation_budget)
        allocation_result = allocate_budget(self.layout, demands, allocation_budget)
        allocation_by_id = {item.module_id: item for item in allocation_result.allocations}
        events.extend(self._lease_events(allocation_result.leases, request_id))

        final_chunks: dict[str, tuple[PromptChunk, ...]] = {}
        usage_rows: list[ModuleUsage] = []
        now = datetime.now(UTC)
        for module_id in self.layout.ordered_module_ids:
            allocation = allocation_by_id[module_id]
            chunks = original_chunks[module_id]
            before = sum(self.token_counter.count_content(chunk.content) for chunk in chunks)
            after = before
            compression_trace: Mapping[str, Any] = {"status": "not_needed"}
            if before > allocation.allocated_tokens:
                chunks, before, after, compression_trace = self._compress_module(
                    module_id, chunks, allocation
                )
                events.append(
                    self._event(
                        "chunk.compressed",
                        request_id,
                        {
                            "module_id": module_id,
                            "before_tokens": before,
                            "after_tokens": after,
                            "target_tokens": allocation.allocated_tokens,
                            "trace": compression_trace,
                        },
                    )
                )
            final_chunks[module_id] = chunks
            fixed_tokens = sum(
                self.token_counter.count_content(chunk.content) for chunk in chunks if chunk.fixed
            )
            pinned_tokens = sum(
                self.token_counter.count_content(chunk.content)
                for chunk in chunks
                if chunk.protection == ProtectionPolicy.PINNED
            )
            previous = self._previous_usage.get(module_id, after)
            change_rate = (after - previous) / max(1, previous)
            self._previous_usage[module_id] = after
            usage_rows.append(
                ModuleUsage(
                    module_id=module_id,
                    floor_tokens=allocation.floor_tokens,
                    target_tokens=allocation.target_tokens,
                    max_tokens=allocation.max_tokens,
                    allocated_tokens=allocation.allocated_tokens,
                    demanded_tokens=allocation.demanded_tokens,
                    used_tokens=after,
                    fixed_tokens=fixed_tokens,
                    variable_tokens=max(0, after - fixed_tokens),
                    pinned_tokens=pinned_tokens,
                    elastic_tokens=max(0, after - pinned_tokens),
                    reclaimable_tokens=max(0, after - pinned_tokens),
                    minimum_retained_tokens=pinned_tokens,
                    local_capacity_tokens=allocation.local_capacity_tokens,
                    borrowed_capacity_tokens=allocation.borrowed_capacity_tokens,
                    lent_capacity_tokens=allocation.lent_capacity_tokens,
                    compressed_from_tokens=before,
                    compressed_to_tokens=after,
                    compression_ratio=(after / before) if before else 1.0,
                    change_rate=change_rate,
                    pressure=_pressure(after, allocation.allocated_tokens),
                    last_updated_at=now,
                )
            )
            events.append(
                self._event(
                    "allocation.granted",
                    request_id,
                    {
                        "module_id": module_id,
                        "allocated_tokens": allocation.allocated_tokens,
                        "used_tokens": after,
                        "borrowed_capacity_tokens": allocation.borrowed_capacity_tokens,
                    },
                    EventPriority.GAUGE,
                )
            )

        rendered_modules = []
        for module_id in self.layout.ordered_module_ids:
            content = "\n\n".join(_render_content(chunk.content) for chunk in final_chunks[module_id])
            if content:
                rendered_modules.append(content)
        rendered = "\n\n".join(rendered_modules)
        prompt_tokens = self.token_counter.count_text(rendered)
        usable_budget = model.input_budget_tokens - self.layout.definition.framework_reserve_tokens
        if prompt_tokens > usable_budget:
            raise AdmissionError(
                f"rendered prompt needs {prompt_tokens} tokens, usable input budget is {usable_budget}"
            )
        events.append(
            self._event(
                "context.rendered",
                request_id,
                {
                    "prompt_tokens": prompt_tokens,
                    "input_budget_tokens": usable_budget,
                    "render_separator_tokens": render_separator_tokens,
                },
            )
        )
        events.append(self._event("request.completed", request_id, {"status": "completed"}))

        self._snapshot_seq += 1
        snapshot = ArenaSnapshot(
            schema_version="1.0",
            arena_id=self.layout.definition.arena_id,
            instance_id=self.instance_id,
            snapshot_seq=self._snapshot_seq,
            captured_at=now,
            request_id=request_id,
            model_profile_id=model.model_profile_id,
            tokenizer_id=model.tokenizer_id,
            token_count_mode=model.count_mode,
            layout_hash=self.layout.layout_hash,
            policy_version=self.layout.definition.policy_version,
            context_limit_tokens=model.context_limit_tokens,
            reserved_output_tokens=model.reserved_output_tokens,
            framework_reserve_tokens=self.layout.definition.framework_reserve_tokens,
            input_budget_tokens=usable_budget,
            used_tokens=prompt_tokens,
            slack_tokens=max(0, usable_budget - prompt_tokens),
            utilization=prompt_tokens / max(1, usable_budget),
            pressure=_pressure(prompt_tokens, usable_budget),
            modules=tuple(usage_rows),
            leases=allocation_result.leases,
            health={"events_dropped": 0},
        )
        self.observations.publish_many(events)
        self.observations.publish_snapshot(snapshot)
        return PreparedContext(
            arena_id=self.layout.definition.arena_id,
            instance_id=self.instance_id,
            request_id=request_id,
            layout_hash=self.layout.layout_hash,
            policy_version=self.layout.definition.policy_version,
            rendered=rendered,
            prompt_tokens=prompt_tokens,
            input_budget_tokens=usable_budget,
            allocations=allocation_result.allocations,
            leases=allocation_result.leases,
            module_contents=final_chunks,
            trace_events=tuple(events),
            snapshot=snapshot,
        )
