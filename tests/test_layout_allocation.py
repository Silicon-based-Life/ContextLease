from __future__ import annotations

import unittest

from contextlease.allocation import allocate_budget
from contextlease.errors import LayoutValidationError
from contextlease.layout import compile_layout, validate_model_budget
from contextlease.models import ArenaDefinition, CompressionStepSpec, ModuleDefinition

PIPELINE = (CompressionStepSpec("builtin.text.boundary_truncate.v1"),)


def module(name: str, floor: int = 5, target: int = 10, maximum: int = 20, **kwargs):
    return ModuleDefinition(
        name, floor, target, maximum,
        reclaim_pipeline=kwargs.pop("reclaim_pipeline", PIPELINE if maximum > target else ()),
        **kwargs,
    )


class LayoutTests(unittest.TestCase):
    def test_layout_hash_is_stable(self):
        definition = ArenaDefinition("stable", (module("a"), module("b", order=1)))
        self.assertEqual(compile_layout(definition).layout_hash, compile_layout(definition).layout_hash)

    def test_duplicate_module_is_rejected(self):
        with self.assertRaisesRegex(LayoutValidationError, "duplicate"):
            compile_layout(ArenaDefinition("bad", (module("a"), module("a"))))

    def test_invalid_budget_order_is_rejected(self):
        with self.assertRaisesRegex(LayoutValidationError, "floor"):
            compile_layout(ArenaDefinition("bad", (module("a", floor=11, target=10),)))

    def test_borrower_requires_release_pipeline(self):
        with self.assertRaisesRegex(LayoutValidationError, "borrowing requires"):
            compile_layout(ArenaDefinition("bad", (module("a", reclaim_pipeline=()),)))

    def test_floor_sum_must_fit_model(self):
        layout = compile_layout(ArenaDefinition("bad", (module("a", floor=10), module("b", floor=10))))
        with self.assertRaisesRegex(LayoutValidationError, "floors require"):
            validate_model_budget(layout, 19)


class AllocationTests(unittest.TestCase):
    def test_allocations_never_exceed_budget(self):
        layout = compile_layout(ArenaDefinition("arena", (module("a"), module("b"))))
        result = allocate_budget(layout, {"a": 20, "b": 20}, 25)
        self.assertLessEqual(sum(item.allocated_tokens for item in result.allocations), 25)

    def test_allocation_respects_max(self):
        layout = compile_layout(ArenaDefinition("arena", (module("a", maximum=12),)))
        result = allocate_budget(layout, {"a": 100}, 100)
        self.assertEqual(result.allocations[0].allocated_tokens, 12)

    def test_unused_target_is_leased_to_borrower(self):
        layout = compile_layout(ArenaDefinition("arena", (module("donor", target=20, maximum=20), module("borrower", target=10, maximum=25))))
        result = allocate_budget(layout, {"donor": 5, "borrower": 22}, 30)
        borrower = next(item for item in result.allocations if item.module_id == "borrower")
        self.assertGreater(borrower.borrowed_capacity_tokens, 0)
        self.assertTrue(any(lease.donor_module_id == "donor" for lease in result.leases))
        self.assertTrue(all(lease.release_pipeline for lease in result.leases))

    def test_non_borrower_stops_at_target(self):
        only = module("a", target=10, maximum=20, can_borrow=False, reclaim_pipeline=())
        layout = compile_layout(ArenaDefinition("arena", (only,)))
        result = allocate_budget(layout, {"a": 20}, 40)
        self.assertEqual(result.allocations[0].allocated_tokens, 10)

    def test_weighted_fill_favors_heavier_module(self):
        layout = compile_layout(ArenaDefinition("arena", (module("a", weight=3), module("b", weight=1))))
        result = allocate_budget(layout, {"a": 20, "b": 20}, 15)
        values = {item.module_id: item.allocated_tokens for item in result.allocations}
        self.assertGreater(values["a"], values["b"])


if __name__ == "__main__":
    unittest.main()
