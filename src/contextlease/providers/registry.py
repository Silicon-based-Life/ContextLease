from __future__ import annotations

from typing import Iterable

from ..errors import ConfigurationError
from .base import SummaryProvider


class SummaryProviderRegistry:
    def __init__(self, providers: Iterable[SummaryProvider] = ()) -> None:
        self._providers: dict[str, SummaryProvider] = {}
        for provider in providers:
            self.register(provider)

    def register(self, provider: SummaryProvider, *, replace: bool = False) -> None:
        if provider.provider_id in self._providers and not replace:
            raise ConfigurationError(f"summary provider already registered: {provider.provider_id}")
        self._providers[provider.provider_id] = provider

    def get(self, provider_id: str) -> SummaryProvider:
        try:
            return self._providers[provider_id]
        except KeyError as exc:
            raise ConfigurationError(f"unknown summary provider: {provider_id}") from exc

    def ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._providers))
