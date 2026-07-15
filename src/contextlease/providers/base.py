from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Protocol


@dataclass(frozen=True, slots=True)
class SummaryRequest:
    content: str
    target_tokens: int
    instructions: str
    required_terms: tuple[str, ...] = ()
    temperature: float = 0.0
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SummaryResponse:
    text: str
    provider_id: str
    model: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


class SummaryProvider(Protocol):
    provider_id: str
    model: str

    def summarize(self, request: SummaryRequest) -> SummaryResponse: ...


class CallableSummaryProvider:
    def __init__(self, provider_id: str, model: str, func: Callable[[SummaryRequest], str]) -> None:
        self.provider_id = provider_id
        self.model = model
        self._func = func

    def summarize(self, request: SummaryRequest) -> SummaryResponse:
        return SummaryResponse(self._func(request), self.provider_id, self.model)
