from __future__ import annotations

from enum import StrEnum


class LifecyclePolicy(StrEnum):
    STATIC = "static"
    SESSION = "session"
    REQUEST = "request"
    TURN = "turn"
    EPHEMERAL = "ephemeral"

    # Source-compatible names from the 0.2 alpha API.  Their serialized values
    # intentionally resolve to the versioned JSON contract above.
    APPLICATION = "static"
    LOOP = "turn"
    EVENT_DRIVEN = "ephemeral"


class AllocationStrategy(StrEnum):
    FIXED = "fixed"
    WEIGHTED = "weighted"
    PRIORITY = "priority"
    ELASTIC = "elastic"

    DEMAND_DRIVEN = "elastic"
    ADAPTIVE = "elastic"
    EXTERNAL = "fixed"


class ProtectionPolicy(StrEnum):
    PINNED = "pinned"
    ELASTIC = "elastic"
    MIXED = "mixed"

    CUSTOM = "mixed"


class ReclaimPolicy(StrEnum):
    NONE = "none"
    BUILTIN_PIPELINE = "builtin_pipeline"
    SEMANTIC_PIPELINE = "semantic_pipeline"
    CUSTOM = "custom"

    DETERMINISTIC = "builtin_pipeline"
    CACHED_VARIANT = "builtin_pipeline"
    REFERENCE = "semantic_pipeline"
    PORTFOLIO = "semantic_pipeline"
    CUSTOM_PLUGIN = "custom"


class RenderTarget(StrEnum):
    TEXT = "text"
    MESSAGES = "messages"
    TOOL_SCHEMA = "tool_schema"
    STRUCTURED = "structured"

    TOOLS = "tool_schema"
    CUSTOM = "structured"


class CountMode(StrEnum):
    ESTIMATED = "estimated"
    EXACT = "exact"
    HYBRID = "hybrid"

    CALIBRATED = "hybrid"


class LeaseState(StrEnum):
    ACTIVE = "active"
    RECLAIMING = "reclaiming"
    RECLAIMED = "reclaimed"
    EXPIRED = "expired"


class Pressure(StrEnum):
    NORMAL = "normal"
    ELEVATED = "elevated"
    CRITICAL = "critical"
    OVERFLOW = "overflow"


class EventPriority(StrEnum):
    GAUGE = "gauge"
    STATE = "state"
