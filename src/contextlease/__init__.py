"""ContextLease: dynamic LLM context budgeting and prompt compression."""

from .allocation import AllocationResult, allocate_budget
from .enums import (
    AllocationStrategy,
    CountMode,
    LifecyclePolicy,
    ProtectionPolicy,
    ReclaimPolicy,
    RenderTarget,
)
from .errors import (
    AdmissionError,
    CompressionError,
    ConfigurationError,
    ContextLeaseError,
    LayoutValidationError,
    ProviderError,
)
from .layout import compile_layout
from .models import (
    ArenaDefinition,
    CompressionStepSpec,
    ContextPlan,
    ModelProfile,
    ModuleContribution,
    ModuleDefinition,
    PreparedChunk,
    PreparedContext,
    PreparedContextPlan,
    PreparedModulePlan,
    PromptChunk,
)
from .native import NativeArena, NativeContextLeaseError
from .observation import ObservationStore
from .runtime import ContextLeaseArena
from .tokenization import CharacterTokenCounter, RegexTokenCounter, TiktokenTokenCounter

__all__ = [
    "AdmissionError", "AllocationResult", "AllocationStrategy", "ArenaDefinition",
    "CharacterTokenCounter", "CompressionError", "CompressionStepSpec", "ConfigurationError",
    "ContextLeaseArena", "ContextLeaseError", "CountMode", "LayoutValidationError", "LifecyclePolicy",
    "ModelProfile", "ModuleContribution", "ModuleDefinition", "NativeArena",
    "NativeContextLeaseError", "ObservationStore",
    "ContextPlan", "PreparedChunk", "PreparedContext", "PreparedContextPlan",
    "PreparedModulePlan", "PromptChunk", "ProtectionPolicy", "ProviderError",
    "ReclaimPolicy", "RegexTokenCounter", "RenderTarget", "TiktokenTokenCounter",
    "allocate_budget", "compile_layout",
]

__version__ = "0.3.0"
