from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol

from ..tokenization import TokenCounter


@dataclass(frozen=True, slots=True)
class CompressionRequest:
    content: Any
    target_tokens: int
    counter: TokenCounter
    required_terms: tuple[str, ...] = ()
    options: Mapping[str, Any] = field(default_factory=dict)
    services: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class CompressionResult:
    algorithm_id: str
    content: Any
    before_tokens: int
    after_tokens: int
    status: str
    lossy: bool
    removed_items: tuple[Any, ...] = ()
    trace: Mapping[str, Any] = field(default_factory=dict)

    @property
    def saved_tokens(self) -> int:
        return max(0, self.before_tokens - self.after_tokens)


class CompressionAlgorithm(Protocol):
    algorithm_id: str
    lossy: bool

    def compress(self, request: CompressionRequest) -> CompressionResult: ...
