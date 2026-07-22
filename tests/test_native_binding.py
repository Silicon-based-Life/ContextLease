from __future__ import annotations

import json
import os
import unittest
from pathlib import Path

from contextlease.native import NativeArena
from contextlease.config import arena_from_dict
from contextlease.layout import compile_layout


@unittest.skipUnless(os.environ.get("CONTEXTLEASE_NATIVE_LIBRARY"), "native library is not configured")
class NativeBindingConformanceTests(unittest.TestCase):
    def test_basic_borrow_fixture(self) -> None:
        fixture_path = Path(__file__).parents[1] / "spec" / "conformance" / "basic-borrow.json"
        fixture = json.loads(fixture_path.read_text(encoding="utf-8"))

        with NativeArena(fixture["definition"]) as arena:
            abi_version = arena.abi_version
            result = arena.prepare(fixture["request"])

        self.assertEqual(1, abi_version)
        self.assertLessEqual(result["prompt_tokens"], fixture["assert"]["max_prompt_tokens"])
        self.assertIn(fixture["assert"]["must_contain"][0], result["rendered"])
        self.assertTrue(
            any(
                lease["borrower_module_id"] == fixture["assert"]["lease_borrower"]
                for lease in result["leases"]
            )
        )

    def test_two_phase_semantic_summary(self) -> None:
        definition = {
            "arena_id": "native-semantic",
            "modules": [
                {
                    "module_id": "memory",
                    "floor_tokens": 0,
                    "target_tokens": 1,
                    "max_tokens": 8,
                    "reclaim_pipeline": [
                        {
                            "algorithm_id": "builtin.semantic.summary.v1",
                            "options": {"provider": "mock"},
                        },
                        {"algorithm_id": "builtin.text.boundary_truncate.v1"},
                    ],
                }
            ],
        }
        request = {
            "request_id": "native-semantic-r1",
            "model": {
                "model_profile_id": "tiny",
                "context_limit_tokens": 4,
                "reserved_output_tokens": 0,
            },
            "contributions": [
                {
                    "module_id": "memory",
                    "chunks": [
                        {
                            "chunk_id": "facts",
                            "content": "alpha beta gamma delta epsilon zeta",
                            "required_terms": ["alpha"],
                        }
                    ],
                }
            ],
        }
        with NativeArena(definition) as arena:
            begin = arena.prepare_begin(request)
            self.assertEqual("needs_semantic", begin["status"])
            semantic_request = begin["semantic_requests"][0]
            prepared = arena.prepare_commit(
                request,
                [
                    {
                        "semantic_request_id": semantic_request["semantic_request_id"],
                        "content": "alpha beta",
                    }
                ],
            )
        self.assertIn("alpha", prepared["rendered"])
        self.assertLessEqual(prepared["prompt_tokens"], prepared["input_budget_tokens"])

    def test_full_contract_and_layout_hash_match_python(self) -> None:
        fixture_path = Path(__file__).parents[1] / "spec" / "conformance" / "contract-fields.json"
        fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
        expected_hash = compile_layout(arena_from_dict(fixture["arena"])).layout_hash
        request = {
            "request_id": "contract-native",
            "model": fixture["model"],
            "contributions": fixture["contributions"],
        }

        with NativeArena(fixture["arena"]) as arena:
            prepared = arena.prepare(request)

        self.assertEqual(expected_hash, prepared["layout_hash"])
        self.assertEqual("hybrid", prepared["token_count_mode"])
        self.assertEqual("1", prepared["tokenizer_version"])

    def test_native_rejects_unknown_fields(self) -> None:
        definition = {
            "arena_id": "unknown-native",
            "modules": [],
            "unexpected": True,
        }
        with self.assertRaisesRegex(Exception, '"code":"configuration_error".*unknown field'):
            NativeArena(definition)


if __name__ == "__main__":
    unittest.main()
