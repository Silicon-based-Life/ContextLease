from __future__ import annotations

from typing import Iterable

from ..errors import ConfigurationError
from .contracts import CompressionAlgorithm


class CompressionRegistry:
    def __init__(self, algorithms: Iterable[CompressionAlgorithm] = ()) -> None:
        self._algorithms: dict[str, CompressionAlgorithm] = {}
        for algorithm in algorithms:
            self.register(algorithm)

    def register(self, algorithm: CompressionAlgorithm, *, replace: bool = False) -> None:
        if algorithm.algorithm_id in self._algorithms and not replace:
            raise ConfigurationError(f"compression algorithm already registered: {algorithm.algorithm_id}")
        self._algorithms[algorithm.algorithm_id] = algorithm

    def get(self, algorithm_id: str) -> CompressionAlgorithm:
        try:
            return self._algorithms[algorithm_id]
        except KeyError as exc:
            raise ConfigurationError(f"unknown compression algorithm: {algorithm_id}") from exc

    def ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._algorithms))
