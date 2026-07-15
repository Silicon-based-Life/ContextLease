from __future__ import annotations

from dataclasses import replace
from typing import Any, Mapping, Sequence

from ..errors import CompressionError
from ..models import CompressionStepSpec
from .contracts import CompressionRequest, CompressionResult
from .registry import CompressionRegistry


class CompressionPipeline:
    def __init__(self, registry: CompressionRegistry) -> None:
        self._registry = registry

    def execute(
        self,
        request: CompressionRequest,
        steps: Sequence[CompressionStepSpec],
        *,
        fail_open: bool = True,
    ) -> CompressionResult:
        current = request.content
        before = request.counter.count_content(current)
        traces: list[Mapping[str, Any]] = []
        lossy = False
        applied: list[str] = []
        removed: list[Any] = []
        for step in steps:
            if request.counter.count_content(current) <= request.target_tokens:
                break
            algorithm = self._registry.get(step.algorithm_id)
            try:
                result = algorithm.compress(
                    replace(request, content=current, options={**request.options, **dict(step.options)})
                )
            except Exception as exc:
                if not fail_open:
                    raise CompressionError(f"compression step {step.algorithm_id} failed: {exc}") from exc
                traces.append({"algorithm_id": step.algorithm_id, "status": "failed", "error": str(exc)})
                continue
            if result.after_tokens > result.before_tokens:
                traces.append({"algorithm_id": step.algorithm_id, "status": "non_monotonic_rejected"})
                continue
            current = result.content
            lossy = lossy or result.lossy
            applied.append(step.algorithm_id)
            removed.extend(result.removed_items)
            traces.append({"algorithm_id": step.algorithm_id, "status": result.status, **dict(result.trace)})

        after = request.counter.count_content(current)
        return CompressionResult(
            algorithm_id="pipeline",
            content=current,
            before_tokens=before,
            after_tokens=after,
            status="target_met" if after <= request.target_tokens else "target_unmet",
            lossy=lossy,
            removed_items=tuple(removed),
            trace={"applied": applied, "steps": traces},
        )
