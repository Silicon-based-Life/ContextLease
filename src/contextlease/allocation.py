from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from .models import CompiledLayout, Lease, ModuleAllocation


@dataclass(frozen=True, slots=True)
class AllocationResult:
    allocations: tuple[ModuleAllocation, ...]
    leases: tuple[Lease, ...]
    unallocated_tokens: int


def _weighted_fill(
    current: dict[str, int],
    caps: Mapping[str, int],
    weights: Mapping[str, float],
    remaining: int,
) -> int:
    active = {module_id for module_id, cap in caps.items() if current[module_id] < cap}
    while remaining > 0 and active:
        total_weight = sum(weights[module_id] for module_id in active)
        progressed = 0
        round_budget = remaining
        for module_id in sorted(active):
            capacity = caps[module_id] - current[module_id]
            if capacity <= 0:
                continue
            share = max(1, int(round_budget * weights[module_id] / total_weight))
            grant = min(capacity, share, remaining)
            current[module_id] += grant
            remaining -= grant
            progressed += grant
            if remaining == 0:
                break
        active = {module_id for module_id in active if current[module_id] < caps[module_id]}
        if progressed == 0:
            break
    return remaining


def allocate_budget(
    layout: CompiledLayout,
    demands: Mapping[str, int],
    input_budget_tokens: int,
) -> AllocationResult:
    modules = layout.definition.modules
    available = input_budget_tokens - layout.definition.framework_reserve_tokens
    current = {
        module.module_id: min(module.floor_tokens, demands.get(module.module_id, 0))
        for module in modules
    }
    remaining = available - sum(current.values())
    weights = {module.module_id: module.weight for module in modules}

    target_caps = {
        module.module_id: min(module.target_tokens, demands.get(module.module_id, 0))
        for module in modules
    }
    remaining = _weighted_fill(current, target_caps, weights, remaining)

    donor_capacity = {
        module.module_id: max(0, module.target_tokens - current[module.module_id])
        for module in modules
        if module.can_lend
    }
    shared_slack = max(0, remaining - sum(donor_capacity.values()))
    lease_records: list[Lease] = []
    borrowed_by = {module.module_id: 0 for module in modules}
    lent_by = {module.module_id: 0 for module in modules}
    donors = [[module_id, amount] for module_id, amount in sorted(donor_capacity.items()) if amount > 0]

    borrowers = sorted(
        (
            module
            for module in modules
            if module.can_borrow
            and demands.get(module.module_id, 0) > module.target_tokens
            and current[module.module_id] < module.max_tokens
        ),
        key=lambda module: (-module.weight, module.order, module.module_id),
    )
    for borrower in borrowers:
        need = min(demands.get(borrower.module_id, 0), borrower.max_tokens) - current[borrower.module_id]
        for donor in donors:
            if need <= 0 or remaining <= 0:
                break
            donor_id, donor_available = donor
            if donor_id == borrower.module_id or donor_available <= 0:
                continue
            grant = min(need, donor_available, remaining)
            if grant <= 0:
                continue
            donor[1] -= grant
            remaining -= grant
            need -= grant
            current[borrower.module_id] += grant
            borrowed_by[borrower.module_id] += grant
            lent_by[donor_id] += grant
            lease_records.append(
                Lease(
                    lease_id=f"{layout.layout_hash}:{donor_id}:{borrower.module_id}",
                    donor_module_id=donor_id,
                    borrower_module_id=borrower.module_id,
                    granted_tokens=grant,
                    currently_used_tokens=grant,
                    reclaimable_tokens=grant,
                    release_pipeline=tuple(step.algorithm_id for step in borrower.reclaim_pipeline),
                )
            )

        if need > 0 and shared_slack > 0 and remaining > 0:
            grant = min(need, shared_slack, remaining)
            shared_slack -= grant
            remaining -= grant
            current[borrower.module_id] += grant
            borrowed_by[borrower.module_id] += grant
            lease_records.append(
                Lease(
                    lease_id=f"{layout.layout_hash}:__arena_slack__:{borrower.module_id}",
                    donor_module_id="__arena_slack__",
                    borrower_module_id=borrower.module_id,
                    granted_tokens=grant,
                    currently_used_tokens=grant,
                    reclaimable_tokens=grant,
                    release_pipeline=tuple(step.algorithm_id for step in borrower.reclaim_pipeline),
                )
            )

    allocations = []
    for module in sorted(modules, key=lambda item: (item.order, item.module_id)):
        borrowed = borrowed_by[module.module_id]
        allocations.append(
            ModuleAllocation(
                module_id=module.module_id,
                floor_tokens=module.floor_tokens,
                target_tokens=module.target_tokens,
                max_tokens=module.max_tokens,
                demanded_tokens=demands.get(module.module_id, 0),
                allocated_tokens=current[module.module_id],
                local_capacity_tokens=max(0, current[module.module_id] - borrowed),
                borrowed_capacity_tokens=borrowed,
                lent_capacity_tokens=lent_by[module.module_id],
            )
        )
    return AllocationResult(tuple(allocations), tuple(lease_records), remaining)
