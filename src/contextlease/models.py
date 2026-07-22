from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Mapping, Sequence

from .enums import (
    AllocationStrategy,
    CountMode,
    EventPriority,
    LeaseState,
    LifecyclePolicy,
    Pressure,
    ProtectionPolicy,
    ReclaimPolicy,
    RenderTarget,
)


def utc_now() -> datetime:
    return datetime.now(UTC)


def to_public_dict(value: Any) -> Any:
    """Serialize public telemetry without leaking prompt content by default."""
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if is_dataclass(value):
        return {key: to_public_dict(item) for key, item in asdict(value).items()}
    if isinstance(value, Mapping):
        return {str(key): to_public_dict(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_public_dict(item) for item in value]
    return value


@dataclass(frozen=True, slots=True)
class CompressionStepSpec:
    algorithm_id: str
    options: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ModuleDefinition:
    module_id: str
    floor_tokens: int
    target_tokens: int
    max_tokens: int
    order: int = 0
    weight: float = 1.0
    lifecycle: LifecyclePolicy = LifecyclePolicy.REQUEST
    allocation: AllocationStrategy = AllocationStrategy.WEIGHTED
    protection: ProtectionPolicy = ProtectionPolicy.MIXED
    reclaim: ReclaimPolicy = ReclaimPolicy.BUILTIN_PIPELINE
    render_target: RenderTarget = RenderTarget.TEXT
    can_borrow: bool = True
    can_lend: bool = True
    reclaim_pipeline: tuple[CompressionStepSpec, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ArenaDefinition:
    arena_id: str
    modules: tuple[ModuleDefinition, ...]
    schema_version: str = "1.0"
    policy_version: str = "1"
    framework_reserve_tokens: int = 0
    admission_policy: str = "reject"
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ModelProfile:
    model_profile_id: str
    context_limit_tokens: int
    reserved_output_tokens: int
    tokenizer_id: str = "regex-estimator-v1"
    tokenizer_version: str = "1"
    count_mode: CountMode = CountMode.ESTIMATED

    @property
    def input_budget_tokens(self) -> int:
        return self.context_limit_tokens - self.reserved_output_tokens


@dataclass(frozen=True, slots=True)
class PromptChunk:
    chunk_id: str
    content: Any
    kind: str = "text"
    fixed: bool = False
    protection: ProtectionPolicy = ProtectionPolicy.ELASTIC
    priority: float = 1.0
    created_at: datetime = field(default_factory=utc_now)
    required_terms: tuple[str, ...] = ()
    dependency_group: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ModuleContribution:
    module_id: str
    chunks: tuple[PromptChunk, ...]
    observed_demand_tokens: int | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ContextPlan:
    model: ModelProfile
    contributions: tuple[ModuleContribution, ...]
    request_id: str | None = None
    schema_version: str = "1.0"


@dataclass(frozen=True, slots=True)
class CompiledLayout:
    definition: ArenaDefinition
    layout_hash: str
    module_by_id: Mapping[str, ModuleDefinition]
    ordered_module_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ModuleAllocation:
    module_id: str
    floor_tokens: int
    target_tokens: int
    max_tokens: int
    demanded_tokens: int
    allocated_tokens: int
    local_capacity_tokens: int
    borrowed_capacity_tokens: int
    lent_capacity_tokens: int


@dataclass(frozen=True, slots=True)
class Lease:
    lease_id: str
    donor_module_id: str
    borrower_module_id: str
    granted_tokens: int
    currently_used_tokens: int
    reclaimable_tokens: int
    release_pipeline: tuple[str, ...]
    state: LeaseState = LeaseState.ACTIVE
    granted_at: datetime = field(default_factory=utc_now)
    reclaim_reason: str | None = None


@dataclass(frozen=True, slots=True)
class TraceEvent:
    event_id: str
    seq: int
    occurred_at: datetime
    arena_id: str
    instance_id: str
    request_id: str | None
    event_type: str
    schema_version: str
    layout_hash: str
    policy_version: str
    payload: Mapping[str, Any]
    priority: EventPriority = EventPriority.STATE


@dataclass(frozen=True, slots=True)
class ModuleUsage:
    module_id: str
    floor_tokens: int
    target_tokens: int
    max_tokens: int
    allocated_tokens: int
    demanded_tokens: int
    used_tokens: int
    fixed_tokens: int
    variable_tokens: int
    pinned_tokens: int
    elastic_tokens: int
    reclaimable_tokens: int
    minimum_retained_tokens: int
    local_capacity_tokens: int
    borrowed_capacity_tokens: int
    lent_capacity_tokens: int
    compressed_from_tokens: int
    compressed_to_tokens: int
    compression_ratio: float
    change_rate: float
    pressure: Pressure
    last_updated_at: datetime


@dataclass(frozen=True, slots=True)
class UsageCalibration:
    model_profile_id: str
    tokenizer_id: str
    tokenizer_version: str
    sample_count: int
    ewma_ratio: float
    safety_multiplier: float
    last_estimated_tokens: int
    last_actual_tokens: int


@dataclass(frozen=True, slots=True)
class PreparedChunk:
    chunk_id: str
    kind: str
    content: Any
    fixed: bool
    protection: ProtectionPolicy
    priority: float
    required_terms: tuple[str, ...]
    dependency_group: str | None
    metadata: Mapping[str, Any]
    token_count: int
    compressed: bool
    source_chunk_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PreparedModulePlan:
    module_id: str
    render_target: RenderTarget
    allocation: ModuleAllocation
    usage: ModuleUsage
    chunks: tuple[PreparedChunk, ...]


@dataclass(frozen=True, slots=True)
class ArenaSnapshot:
    schema_version: str
    arena_id: str
    instance_id: str
    snapshot_seq: int
    captured_at: datetime
    request_id: str | None
    model_profile_id: str
    tokenizer_id: str
    tokenizer_version: str
    token_count_mode: CountMode
    layout_hash: str
    policy_version: str
    context_limit_tokens: int
    reserved_output_tokens: int
    framework_reserve_tokens: int
    input_budget_tokens: int
    used_tokens: int
    slack_tokens: int
    utilization: float
    pressure: Pressure
    modules: tuple[ModuleUsage, ...]
    leases: tuple[Lease, ...]
    calibration: UsageCalibration | None = None
    health: Mapping[str, Any] = field(default_factory=dict)

    def public_dict(self) -> dict[str, Any]:
        return to_public_dict(self)


@dataclass(frozen=True, slots=True)
class PreparedContextPlan:
    schema_version: str
    core_version: str
    arena_id: str
    instance_id: str
    request_id: str
    layout_hash: str
    policy_version: str
    model_profile_id: str
    tokenizer_id: str
    tokenizer_version: str
    token_count_mode: CountMode
    context_limit_tokens: int
    reserved_output_tokens: int
    framework_reserve_tokens: int
    rendered: str
    prompt_tokens: int
    input_budget_tokens: int
    slack_tokens: int
    pressure: Pressure
    allocations: tuple[ModuleAllocation, ...]
    leases: tuple[Lease, ...]
    modules: tuple[ModuleUsage, ...]
    module_plans: tuple[PreparedModulePlan, ...]
    trace_events: tuple[TraceEvent, ...]
    snapshot: ArenaSnapshot
    calibration: UsageCalibration | None = None

    @property
    def module_contents(self) -> Mapping[str, tuple[PromptChunk, ...]]:
        """Compatibility view derived from the canonical structured plan."""
        return {
            module.module_id: tuple(
                PromptChunk(
                    chunk_id=chunk.chunk_id,
                    content=chunk.content,
                    kind=chunk.kind,
                    fixed=chunk.fixed,
                    protection=chunk.protection,
                    priority=chunk.priority,
                    required_terms=chunk.required_terms,
                    dependency_group=chunk.dependency_group,
                    metadata=chunk.metadata,
                )
                for chunk in module.chunks
            )
            for module in self.module_plans
        }


# Source-compatible name retained while the public contract moves to the
# explicit PreparedContextPlan terminology.
PreparedContext = PreparedContextPlan
