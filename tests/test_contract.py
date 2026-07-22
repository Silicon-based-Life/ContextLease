from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import fields
from pathlib import Path

from contextlease.config import (
    arena_from_dict,
    contributions_from_dict,
    load_json_config,
    model_from_dict,
)
from contextlease.enums import (
    AllocationStrategy,
    CountMode,
    LifecyclePolicy,
    ProtectionPolicy,
    ReclaimPolicy,
    RenderTarget,
)
from contextlease.errors import ConfigurationError
from contextlease.models import ContextPlan, PreparedContextPlan


ROOT = Path(__file__).parents[1]
SCHEMA = json.loads(
    (ROOT / "src" / "contextlease" / "schema" / "contextlease.schema.json").read_text(encoding="utf-8")
)
RUNTIME_SCHEMA = json.loads(
    (ROOT / "src" / "contextlease" / "schema" / "contextlease.runtime.schema.json").read_text(
        encoding="utf-8"
    )
)
FIXTURE = ROOT / "spec" / "conformance" / "contract-fields.json"


class ContractTests(unittest.TestCase):
    def test_prepared_python_dto_matches_runtime_schema(self) -> None:
        self.assertEqual(
            {field.name for field in fields(PreparedContextPlan)},
            set(RUNTIME_SCHEMA["$defs"]["prepared_context_plan"]["properties"]),
        )
        self.assertEqual(
            {field.name for field in fields(ContextPlan)},
            set(RUNTIME_SCHEMA["$defs"]["context_plan"]["properties"]),
        )

    def test_schema_enums_match_python_contract(self) -> None:
        definitions = SCHEMA["$defs"]
        pairs = (
            (LifecyclePolicy, definitions["module"]["properties"]["lifecycle"]["enum"]),
            (AllocationStrategy, definitions["module"]["properties"]["allocation"]["enum"]),
            (ProtectionPolicy, definitions["module"]["properties"]["protection"]["enum"]),
            (ReclaimPolicy, definitions["module"]["properties"]["reclaim"]["enum"]),
            (RenderTarget, definitions["module"]["properties"]["render_target"]["enum"]),
            (CountMode, definitions["model"]["properties"]["count_mode"]["enum"]),
        )
        for enum_type, schema_values in pairs:
            with self.subTest(enum=enum_type.__name__):
                self.assertEqual({member.value for member in enum_type}, set(schema_values))

    def test_full_contract_fixture_is_preserved(self) -> None:
        data = load_json_config(FIXTURE)
        arena = arena_from_dict(data["arena"])
        model = model_from_dict(data["model"])
        contributions = contributions_from_dict(data["contributions"])

        module = arena.modules[0]
        chunk = contributions[0].chunks[0]
        self.assertEqual(module.lifecycle, LifecyclePolicy.SESSION)
        self.assertEqual(module.allocation, AllocationStrategy.PRIORITY)
        self.assertEqual(module.reclaim, ReclaimPolicy.SEMANTIC_PIPELINE)
        self.assertEqual(module.render_target, RenderTarget.MESSAGES)
        self.assertEqual(model.count_mode, CountMode.HYBRID)
        self.assertEqual(chunk.kind, "message")
        self.assertEqual(chunk.metadata["source"], "fixture")
        self.assertEqual(contributions[0].observed_demand_tokens, 2)
        self.assertEqual(contributions[0].metadata["producer"], "fixture")

    def test_unknown_fields_are_rejected_at_every_input_level(self) -> None:
        data = json.loads(FIXTURE.read_text(encoding="utf-8"))
        mutations = (
            (data, "unknown_root"),
            (data["arena"], "unknown_arena"),
            (data["arena"]["modules"][0], "unknown_module"),
            (data["model"], "unknown_model"),
            (data["contributions"][0], "unknown_contribution"),
            (data["contributions"][0]["chunks"][0], "unknown_chunk"),
        )
        for target, key in mutations:
            target[key] = True
            try:
                with tempfile.TemporaryDirectory() as directory:
                    path = Path(directory) / "invalid.json"
                    path.write_text(json.dumps(data), encoding="utf-8")
                    with self.assertRaisesRegex(ConfigurationError, "unknown field"):
                        load_json_config(path)
            finally:
                del target[key]

    def test_invalid_enum_and_range_values_are_rejected(self) -> None:
        cases = (
            (("arena", "modules", 0, "allocation"), "not-a-policy", "expected one of"),
            (("model", "count_mode"), "not-a-mode", "expected one of"),
            (("contributions", 0, "observed_demand_tokens"), -1, ">= 0"),
        )
        for path_parts, invalid_value, expected_error in cases:
            data = json.loads(FIXTURE.read_text(encoding="utf-8"))
            target = data
            for part in path_parts[:-1]:
                target = target[part]
            target[path_parts[-1]] = invalid_value
            with self.subTest(path=path_parts), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "invalid.json"
                path.write_text(json.dumps(data), encoding="utf-8")
                with self.assertRaisesRegex(ConfigurationError, expected_error):
                    load_json_config(path)


if __name__ == "__main__":
    unittest.main()
