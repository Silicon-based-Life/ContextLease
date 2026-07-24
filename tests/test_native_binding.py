from __future__ import annotations

import json
import os
import unittest
from pathlib import Path

from contextlease.config import arena_from_dict
from contextlease.layout import compile_layout
from contextlease.native import NativeArena
from contextlease.tokenization import CharacterTokenCounter


@unittest.skipUnless(os.environ.get("CONTEXTLEASE_NATIVE_LIBRARY"), "native library is not configured")
class NativeBindingConformanceTests(unittest.TestCase):
    def test_basic_borrow_fixture(self) -> None:
        fixture_path = Path(__file__).parents[1] / "spec" / "conformance" / "basic-borrow.json"
        fixture = json.loads(fixture_path.read_text(encoding="utf-8"))

        with NativeArena(fixture["definition"]) as arena:
            abi_version = arena.abi_version
            result = arena.prepare(fixture["request"])

        self.assertEqual(2, abi_version)
        self.assertLessEqual(result["prompt_tokens"], fixture["assert"]["max_prompt_tokens"])
        self.assertIn(fixture["assert"]["must_contain"][0], result["rendered"])
        self.assertTrue(
            any(
                lease["borrower_module_id"] == fixture["assert"]["lease_borrower"]
                for lease in result["leases"]
            )
        )
        self.assertTrue(result["module_plans"])
        self.assertTrue(result["trace_events"])
        runtime_schema = json.loads(
            (
                Path(__file__).parents[1]
                / "src"
                / "contextlease"
                / "schema"
                / "contextlease.runtime.schema.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(
            set(result),
            set(runtime_schema["$defs"]["prepared_context_plan"]["properties"]),
        )

    def test_exact_tokenizer_snapshot_events_and_usage_calibration(self) -> None:
        definition = {
            "arena_id": "native-kernel-api",
            "modules": [
                {
                    "module_id": "memory",
                    "floor_tokens": 0,
                    "target_tokens": 20,
                    "max_tokens": 20,
                }
            ],
        }
        request = {
            "request_id": "native-kernel-r1",
            "model": {
                "model_profile_id": "char",
                "context_limit_tokens": 20,
                "reserved_output_tokens": 0,
                "tokenizer_id": "character-v1",
                "tokenizer_version": "1",
                "count_mode": "exact",
            },
            "contributions": [
                {
                    "module_id": "memory",
                    "chunks": [{"chunk_id": "facts", "content": "alpha beta"}],
                }
            ],
        }
        with NativeArena(definition) as arena:
            arena.set_token_counter(CharacterTokenCounter())
            prepared = arena.prepare(request)
            snapshot = arena.snapshot()
            events = arena.events()
            calibration = arena.record_usage("native-kernel-r1", 12)

        self.assertEqual(prepared["prompt_tokens"], len("alpha beta"))
        self.assertEqual(snapshot["request_id"], "native-kernel-r1")
        self.assertTrue(any(item["event_type"] == "request.prepared" for item in events))
        self.assertEqual(calibration["sample_count"], 1)

    def test_tokenizer_callback_failure_aborts_prepare(self) -> None:
        class BrokenCounter:
            counter_id = "broken"

            def count_text(self, _text: str) -> int:
                raise RuntimeError("tokenizer offline")

            def count_content(self, _content: object) -> int:
                raise RuntimeError("tokenizer offline")

        definition = {
            "arena_id": "native-tokenizer-error",
            "modules": [
                {"module_id": "memory", "floor_tokens": 0, "target_tokens": 8, "max_tokens": 8}
            ],
        }
        request = {
            "model": {
                "model_profile_id": "exact",
                "context_limit_tokens": 8,
                "reserved_output_tokens": 0,
                "count_mode": "exact",
            },
            "contributions": [
                {"module_id": "memory", "chunks": [{"chunk_id": "c", "content": "x"}]}
            ],
        }
        with NativeArena(definition) as arena:
            arena.set_token_counter(BrokenCounter())
            with self.assertRaisesRegex(Exception, "tokenizer offline"):
                arena.prepare(request)
            self.assertIsNone(arena.snapshot())
            self.assertEqual(arena.events(), [])

    def test_failed_prepare_does_not_commit_partial_state(self) -> None:
        definition = {
            "arena_id": "native-transaction",
            "modules": [
                {"module_id": "system", "floor_tokens": 0, "target_tokens": 4, "max_tokens": 4}
            ],
        }
        model = {
            "model_profile_id": "char",
            "context_limit_tokens": 4,
            "reserved_output_tokens": 0,
            "tokenizer_id": "character-v1",
            "count_mode": "exact",
        }
        with NativeArena(definition) as arena:
            arena.set_token_counter(CharacterTokenCounter())
            arena.prepare(
                {
                    "request_id": "committed",
                    "model": model,
                    "contributions": [
                        {"module_id": "system", "chunks": [{"chunk_id": "ok", "content": "ok"}]}
                    ],
                }
            )
            before_snapshot = arena.snapshot()
            before_events = arena.events()
            with self.assertRaisesRegex(Exception, "(pinned|protected) content exceeds allocation"):
                arena.prepare(
                    {
                        "request_id": "rejected",
                        "model": model,
                        "contributions": [
                            {
                                "module_id": "system",
                                "chunks": [
                                    {
                                        "chunk_id": "too-large",
                                        "content": "12345",
                                        "protection": "pinned",
                                    }
                                ],
                            }
                        ],
                    }
                )
            after_snapshot = arena.snapshot()
            after_events = arena.events()
        self.assertEqual(before_snapshot["snapshot_seq"], after_snapshot["snapshot_seq"])
        self.assertEqual(before_events, after_events)

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
