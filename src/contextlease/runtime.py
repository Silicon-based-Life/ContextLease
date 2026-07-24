from __future__ import annotations

import json
import threading
from datetime import UTC, datetime
from typing import Any, Iterable, Mapping

from .enums import CountMode, EventPriority, LeaseState, Pressure, ProtectionPolicy, RenderTarget
from .errors import AdmissionError, ConfigurationError, LayoutValidationError
from .layout import compile_layout
from .models import (
    ArenaDefinition,
    ArenaSnapshot,
    Lease,
    ModelProfile,
    ModuleAllocation,
    ModuleContribution,
    ModuleUsage,
    PreparedChunk,
    PreparedContextPlan,
    PreparedModulePlan,
    TraceEvent,
    UsageCalibration,
    to_public_dict,
)
from .native import NativeArena, NativeContextLeaseError
from .observation import ObservationStore
from .providers import SummaryProviderRegistry, SummaryRequest
from .tokenization import TokenCounter


def _datetime(value: str | None) -> datetime:
    if not value:
        return datetime.now(UTC)
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return datetime.now(UTC)


def _allocation(value: Mapping[str, Any]) -> ModuleAllocation:
    return ModuleAllocation(**{key: int(item) if key != "module_id" else str(item) for key, item in value.items()})


def _lease(value: Mapping[str, Any]) -> Lease:
    return Lease(
        lease_id=str(value["lease_id"]),
        donor_module_id=str(value["donor_module_id"]),
        borrower_module_id=str(value["borrower_module_id"]),
        granted_tokens=int(value["granted_tokens"]),
        currently_used_tokens=int(value["currently_used_tokens"]),
        reclaimable_tokens=int(value["reclaimable_tokens"]),
        release_pipeline=tuple(map(str, value.get("release_pipeline", ()))),
        state=LeaseState(value.get("state", "active")),
        reclaim_reason=value.get("reclaim_reason"),
    )


def _usage(value: Mapping[str, Any]) -> ModuleUsage:
    return ModuleUsage(
        module_id=str(value["module_id"]),
        floor_tokens=int(value["floor_tokens"]),
        target_tokens=int(value["target_tokens"]),
        max_tokens=int(value["max_tokens"]),
        allocated_tokens=int(value["allocated_tokens"]),
        demanded_tokens=int(value["demanded_tokens"]),
        used_tokens=int(value["used_tokens"]),
        fixed_tokens=int(value["fixed_tokens"]),
        variable_tokens=int(value["variable_tokens"]),
        pinned_tokens=int(value["pinned_tokens"]),
        elastic_tokens=int(value["elastic_tokens"]),
        reclaimable_tokens=int(value["reclaimable_tokens"]),
        minimum_retained_tokens=int(value["minimum_retained_tokens"]),
        local_capacity_tokens=int(value["local_capacity_tokens"]),
        borrowed_capacity_tokens=int(value["borrowed_capacity_tokens"]),
        lent_capacity_tokens=int(value["lent_capacity_tokens"]),
        compressed_from_tokens=int(value["compressed_from_tokens"]),
        compressed_to_tokens=int(value["compressed_to_tokens"]),
        compression_ratio=float(value["compression_ratio"]),
        change_rate=float(value["change_rate"]),
        pressure=Pressure(value["pressure"]),
        last_updated_at=_datetime(value.get("last_updated_at")),
    )


def _calibration(value: Mapping[str, Any] | None) -> UsageCalibration | None:
    if not value:
        return None
    return UsageCalibration(
        model_profile_id=str(value["model_profile_id"]),
        tokenizer_id=str(value["tokenizer_id"]),
        tokenizer_version=str(value["tokenizer_version"]),
        sample_count=int(value["sample_count"]),
        ewma_ratio=float(value["ewma_ratio"]),
        safety_multiplier=float(value["safety_multiplier"]),
        last_estimated_tokens=int(value["last_estimated_tokens"]),
        last_actual_tokens=int(value["last_actual_tokens"]),
    )


class ContextLeaseArena:
    """Pythonic facade over the canonical Rust allocation/reclaim kernel."""

    def __init__(
        self,
        definition: ArenaDefinition,
        *,
        token_counter: TokenCounter | None = None,
        compression_registry: Any | None = None,
        summary_providers: SummaryProviderRegistry | None = None,
        observations: ObservationStore | None = None,
        instance_id: str | None = None,
        native_library_path: str | None = None,
    ) -> None:
        if compression_registry is not None:
            raise ConfigurationError(
                "Python compression registries are not execution cores; register a Rust algorithm or use a semantic provider"
            )
        self.layout = compile_layout(definition)
        self.summary_providers = summary_providers or SummaryProviderRegistry()
        self.observations = observations or ObservationStore()
        self._instance_id_override = instance_id
        self._prepare_lock = threading.RLock()
        self._native = NativeArena(to_public_dict(definition), library_path=native_library_path)
        if token_counter is not None:
            self._native.set_token_counter(token_counter)

    @property
    def native(self) -> NativeArena:
        return self._native

    def prepare(
        self,
        model: ModelProfile,
        contributions: Iterable[ModuleContribution],
        *,
        request_id: str | None = None,
    ) -> PreparedContextPlan:
        payload = self._request_payload(model, tuple(contributions), request_id)
        with self._prepare_lock:
            try:
                begin = self._native.prepare_begin(payload)
                if begin["status"] == "ready":
                    raw = begin["prepared"]
                else:
                    semantic_results = [
                        self._summarize(item) for item in begin.get("semantic_requests", ())
                    ]
                    raw = self._native.prepare_commit(payload, semantic_results)
            except NativeContextLeaseError as error:
                self._raise_native(error)
            prepared = self._prepared(raw)
            self.observations.publish_many(prepared.trace_events)
            self.observations.publish_snapshot(prepared.snapshot)
            return prepared

    def record_usage(self, request_id: str, actual_input_tokens: int) -> UsageCalibration:
        with self._prepare_lock:
            try:
                value = self._native.record_usage(request_id, actual_input_tokens)
                arena_id = self.layout.definition.arena_id
                existing = self.observations.events_after(arena_id, 0, 10_000)
                after_seq = existing[-1].seq if existing else 0
                raw_events = self._native.events(after_seq=after_seq)
                raw_snapshot = self._native.snapshot()
            except NativeContextLeaseError as error:
                self._raise_native(error)
            instance_id = self._instance_id_override or str(
                raw_snapshot["instance_id"] if raw_snapshot else ""
            )
            self.observations.publish_many(
                self._event(item, instance_id) for item in raw_events
            )
            if raw_snapshot:
                self.observations.publish_snapshot(
                    self._snapshot(raw_snapshot, instance_id)
                )
        calibration = _calibration(value)
        assert calibration is not None
        return calibration

    def close(self) -> None:
        self._native.close()

    def __enter__(self) -> "ContextLeaseArena":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _summarize(self, value: Mapping[str, Any]) -> dict[str, str]:
        options = dict(value.get("options", {}))
        provider = self.summary_providers.get(str(value["provider_id"]))
        response = provider.summarize(
            SummaryRequest(
                content=str(value["source_text"]),
                target_tokens=int(value["target_tokens"]),
                instructions=str(
                    options.get("instructions", "Preserve facts, qualifiers, and unresolved items.")
                ),
                required_terms=tuple(map(str, value.get("required_terms", ()))),
                temperature=float(options.get("temperature", 0.0)),
                metadata={
                    "arena_id": self.layout.definition.arena_id,
                    "module_id": value["module_id"],
                    "algorithm_id": value["algorithm_id"],
                },
            )
        )
        return {
            "semantic_request_id": str(value["semantic_request_id"]),
            "content": response.text,
        }

    def _request_payload(
        self,
        model: ModelProfile,
        contributions: tuple[ModuleContribution, ...],
        request_id: str | None,
    ) -> dict[str, Any]:
        return {
            "schema_version": "1.0",
            "request_id": request_id,
            "model": to_public_dict(model),
            "contributions": [
                {
                    "module_id": contribution.module_id,
                    "observed_demand_tokens": contribution.observed_demand_tokens,
                    "metadata": to_public_dict(contribution.metadata),
                    "chunks": [
                        {
                            "chunk_id": chunk.chunk_id,
                            "content": to_public_dict(chunk.content),
                            "kind": chunk.kind,
                            "fixed": chunk.fixed,
                            "protection": chunk.protection.value,
                            "priority": chunk.priority,
                            "required_terms": list(chunk.required_terms),
                            "dependency_group": chunk.dependency_group,
                            "metadata": to_public_dict(chunk.metadata),
                        }
                        for chunk in contribution.chunks
                    ],
                }
                for contribution in contributions
            ],
        }

    def _prepared(self, value: Mapping[str, Any]) -> PreparedContextPlan:
        allocations = tuple(_allocation(item) for item in value["allocations"])
        leases = tuple(_lease(item) for item in value["leases"])
        usages = tuple(_usage(item) for item in value["modules"])
        plans: list[PreparedModulePlan] = []
        for item in value["module_plans"]:
            chunks = tuple(
                PreparedChunk(
                    chunk_id=str(chunk["chunk_id"]),
                    kind=str(chunk["kind"]),
                    content=chunk["content"],
                    fixed=bool(chunk["fixed"]),
                    protection=ProtectionPolicy(chunk["protection"]),
                    priority=float(chunk["priority"]),
                    required_terms=tuple(map(str, chunk.get("required_terms", ()))),
                    dependency_group=chunk.get("dependency_group"),
                    metadata=dict(chunk.get("metadata", {})),
                    token_count=int(chunk["token_count"]),
                    compressed=bool(chunk["compressed"]),
                    source_chunk_ids=tuple(map(str, chunk.get("source_chunk_ids", ()))),
                )
                for chunk in item["chunks"]
            )
            allocation = _allocation(item["allocation"])
            usage = _usage(item["usage"])
            plans.append(
                PreparedModulePlan(
                    module_id=str(item["module_id"]),
                    render_target=RenderTarget(item["render_target"]),
                    allocation=allocation,
                    usage=usage,
                    chunks=chunks,
                )
            )
        instance_id = self._instance_id_override or str(value["instance_id"])
        events = tuple(self._event(item, instance_id) for item in value.get("trace_events", ()))
        snapshot = self._snapshot(value["snapshot"], instance_id)
        return PreparedContextPlan(
            schema_version=str(value["schema_version"]),
            core_version=str(value["core_version"]),
            arena_id=str(value["arena_id"]),
            instance_id=instance_id,
            request_id=str(value["request_id"]),
            layout_hash=str(value["layout_hash"]),
            policy_version=str(value["policy_version"]),
            model_profile_id=str(value["model_profile_id"]),
            tokenizer_id=str(value["tokenizer_id"]),
            tokenizer_version=str(value["tokenizer_version"]),
            token_count_mode=CountMode(value["token_count_mode"]),
            context_limit_tokens=int(value["context_limit_tokens"]),
            reserved_output_tokens=int(value["reserved_output_tokens"]),
            framework_reserve_tokens=int(value["framework_reserve_tokens"]),
            rendered=str(value["rendered"]),
            prompt_tokens=int(value["prompt_tokens"]),
            input_budget_tokens=int(value["input_budget_tokens"]),
            slack_tokens=int(value["slack_tokens"]),
            pressure=Pressure(value["pressure"]),
            allocations=allocations,
            leases=leases,
            modules=usages,
            module_plans=tuple(plans),
            trace_events=events,
            snapshot=snapshot,
            calibration=_calibration(value.get("calibration")),
        )

    def _event(self, value: Mapping[str, Any], instance_id: str) -> TraceEvent:
        return TraceEvent(
            event_id=str(value["event_id"]),
            seq=int(value["seq"]),
            occurred_at=_datetime(value.get("occurred_at")),
            arena_id=str(value["arena_id"]),
            instance_id=instance_id,
            request_id=value.get("request_id"),
            event_type=str(value["event_type"]),
            schema_version=str(value["schema_version"]),
            layout_hash=str(value["layout_hash"]),
            policy_version=str(value["policy_version"]),
            payload=dict(value.get("payload", {})),
            priority=EventPriority(value.get("priority", "state")),
        )

    def _snapshot(self, value: Mapping[str, Any], instance_id: str) -> ArenaSnapshot:
        return ArenaSnapshot(
            schema_version=str(value["schema_version"]),
            arena_id=str(value["arena_id"]),
            instance_id=instance_id,
            snapshot_seq=int(value["snapshot_seq"]),
            captured_at=_datetime(value.get("captured_at")),
            request_id=value.get("request_id"),
            model_profile_id=str(value["model_profile_id"]),
            tokenizer_id=str(value["tokenizer_id"]),
            tokenizer_version=str(value["tokenizer_version"]),
            token_count_mode=CountMode(value["token_count_mode"]),
            layout_hash=str(value["layout_hash"]),
            policy_version=str(value["policy_version"]),
            context_limit_tokens=int(value["context_limit_tokens"]),
            reserved_output_tokens=int(value["reserved_output_tokens"]),
            framework_reserve_tokens=int(value["framework_reserve_tokens"]),
            input_budget_tokens=int(value["input_budget_tokens"]),
            used_tokens=int(value["used_tokens"]),
            slack_tokens=int(value["slack_tokens"]),
            utilization=float(value["utilization"]),
            pressure=Pressure(value["pressure"]),
            modules=tuple(_usage(item) for item in value["modules"]),
            leases=tuple(_lease(item) for item in value["leases"]),
            calibration=_calibration(value.get("calibration")),
            health=dict(value.get("health", {})),
        )

    @staticmethod
    def _raise_native(error: NativeContextLeaseError) -> None:
        message = str(error)
        try:
            envelope = json.loads(message)
            code = str(envelope.get("code", "native_error"))
            detail = str(envelope.get("message", message))
        except json.JSONDecodeError:
            code, detail = "native_error", message
        if code == "admission_error":
            raise AdmissionError(detail) from error
        if code == "layout_validation_error":
            raise LayoutValidationError(detail) from error
        if code in {
            "configuration_error",
            "tokenizer_unavailable",
            "usage_observation_unknown",
        }:
            raise ConfigurationError(detail) from error
        raise NativeContextLeaseError(detail) from error
