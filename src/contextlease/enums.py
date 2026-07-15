from __future__ import annotations

from enum import StrEnum


class LifecyclePolicy(StrEnum):
    APPLICATION = "application"
    SESSION = "session"
    REQUEST = "request"
    TURN = "turn"
    LOOP = "loop"
    EVENT_DRIVEN = "event_driven"


class AllocationStrategy(StrEnum):
    FIXED = "fixed"
    WEIGHTED = "weighted"
    DEMAND_DRIVEN = "demand_driven"
    ADAPTIVE = "adaptive"
    EXTERNAL = "external"


class ProtectionPolicy(StrEnum):
    PINNED = "pinned"
    ELASTIC = "elastic"
    MIXED = "mixed"
    CUSTOM = "custom"


class ReclaimPolicy(StrEnum):
    NONE = "none"
    BUILTIN_PIPELINE = "builtin_pipeline"
    DETERMINISTIC = "deterministic"
    CACHED_VARIANT = "cached_variant"
    REFERENCE = "reference"
    PORTFOLIO = "portfolio"
    CUSTOM_PLUGIN = "custom_plugin"


class RenderTarget(StrEnum):
    TEXT = "text"
    MESSAGES = "messages"
    TOOLS = "tools"
    CUSTOM = "custom"


class CountMode(StrEnum):
    ESTIMATED = "estimated"
    EXACT = "exact"
    CALIBRATED = "calibrated"


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
