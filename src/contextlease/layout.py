from __future__ import annotations

import hashlib
import json

from .errors import LayoutValidationError
from .models import ArenaDefinition, CompiledLayout, to_public_dict


def compile_layout(definition: ArenaDefinition) -> CompiledLayout:
    if not definition.arena_id.strip():
        raise LayoutValidationError("arena_id must not be empty")
    if not definition.modules:
        raise LayoutValidationError("at least one module is required")
    if definition.framework_reserve_tokens < 0:
        raise LayoutValidationError("framework_reserve_tokens must be non-negative")

    module_by_id = {}
    for module in definition.modules:
        if not module.module_id.strip():
            raise LayoutValidationError("module_id must not be empty")
        if module.module_id in module_by_id:
            raise LayoutValidationError(f"duplicate module_id: {module.module_id}")
        if not (0 <= module.floor_tokens <= module.target_tokens <= module.max_tokens):
            raise LayoutValidationError(
                f"module {module.module_id}: expected 0 <= floor <= target <= max"
            )
        if module.weight <= 0:
            raise LayoutValidationError(f"module {module.module_id}: weight must be positive")
        if module.can_borrow and module.max_tokens > module.target_tokens and not module.reclaim_pipeline:
            raise LayoutValidationError(
                f"module {module.module_id}: borrowing requires a registered reclaim_pipeline"
            )
        module_by_id[module.module_id] = module

    payload = json.dumps(to_public_dict(definition), sort_keys=True, separators=(",", ":"))
    layout_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]
    ordered = tuple(
        module.module_id for module in sorted(definition.modules, key=lambda item: (item.order, item.module_id))
    )
    return CompiledLayout(definition, layout_hash, module_by_id, ordered)


def validate_model_budget(layout: CompiledLayout, input_budget_tokens: int) -> None:
    available = input_budget_tokens - layout.definition.framework_reserve_tokens
    if available <= 0:
        raise LayoutValidationError("model input budget is exhausted by framework reserve")
    total_floor = sum(module.floor_tokens for module in layout.definition.modules)
    if total_floor > available:
        raise LayoutValidationError(
            f"module floors require {total_floor} tokens but only {available} are available"
        )
