class ContextLeaseError(Exception):
    """Base exception for ContextLease."""


class ConfigurationError(ContextLeaseError):
    """Raised when a layout or provider configuration is invalid."""


class LayoutValidationError(ConfigurationError):
    """Raised when an ArenaDefinition violates a layout invariant."""


class AdmissionError(ContextLeaseError):
    """Raised when protected content cannot fit in the available context."""


class CompressionError(ContextLeaseError):
    """Raised when an explicitly configured compression pipeline fails."""


class ProviderError(ContextLeaseError):
    """Raised when an LLM summary provider cannot produce a valid result."""
