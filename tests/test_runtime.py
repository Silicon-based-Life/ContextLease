from __future__ import annotations

import unittest
from concurrent.futures import ThreadPoolExecutor

from contextlease.enums import CountMode, ProtectionPolicy
from contextlease.errors import AdmissionError
from contextlease.models import ArenaDefinition, CompressionStepSpec, ModelProfile, ModuleContribution, ModuleDefinition, PromptChunk
from contextlease.runtime import ContextLeaseArena
from contextlease.tokenization import CharacterTokenCounter
from contextlease.providers import CallableSummaryProvider, SummaryProviderRegistry


TRUNCATE = (CompressionStepSpec("builtin.text.boundary_truncate.v1"),)


class RuntimeTests(unittest.TestCase):
    def make_arena(self):
        definition = ArenaDefinition(
            "runtime-test",
            (
                ModuleDefinition("donor", 20, 20, 20, order=0, can_borrow=False, reclaim_pipeline=()),
                ModuleDefinition("borrower", 1, 10, 25, order=1, reclaim_pipeline=TRUNCATE),
            ),
        )
        return ContextLeaseArena(definition, token_counter=CharacterTokenCounter(), instance_id="instance-test")

    def test_prepare_emits_snapshot_without_prompt_body(self):
        arena = self.make_arena()
        result = arena.prepare(ModelProfile("char-30", 30, 0, count_mode=CountMode.EXACT), [ModuleContribution("donor", (PromptChunk("d", "short"),)), ModuleContribution("borrower", (PromptChunk("b", "SECRET-CONTENT-12345"),))], request_id="r1")
        public = arena.observations.public_snapshot("runtime-test")
        self.assertEqual(result.request_id, "r1")
        self.assertNotIn("SECRET-CONTENT", str(public))
        self.assertLessEqual(result.prompt_tokens, result.input_budget_tokens)
        self.assertEqual(result.module_plans[1].module_id, "borrower")
        self.assertTrue(result.module_plans[1].chunks)

    def test_actual_usage_calibrates_estimated_future_requests(self):
        definition = ArenaDefinition(
            "calibration-test",
            (ModuleDefinition("memory", 0, 20, 20, can_borrow=False),),
        )
        arena = ContextLeaseArena(definition)
        model = ModelProfile("estimated", 20, 0)
        contribution = [ModuleContribution("memory", (PromptChunk("facts", "one two"),))]
        first = arena.prepare(model, contribution, request_id="usage-1")
        calibration = arena.record_usage("usage-1", first.prompt_tokens * 2)
        second = arena.prepare(model, contribution, request_id="usage-2")
        self.assertEqual(calibration.sample_count, 1)
        self.assertGreaterEqual(second.prompt_tokens, first.prompt_tokens)
        self.assertTrue(
            any(
                event.event_type == "usage.calibrated"
                for event in arena.observations.events_after("calibration-test", 0)
            )
        )

    def test_python_facade_executes_native_two_phase_semantic_request(self):
        definition = ArenaDefinition(
            "semantic-facade",
            (
                ModuleDefinition(
                    "memory",
                    0,
                    1,
                    8,
                    reclaim_pipeline=(
                        CompressionStepSpec(
                            "builtin.semantic.summary.v1", {"provider": "mock"}
                        ),
                        CompressionStepSpec("builtin.text.boundary_truncate.v1"),
                    ),
                ),
            ),
        )
        providers = SummaryProviderRegistry(
            [CallableSummaryProvider("mock", "mock-model", lambda _request: "alpha beta")]
        )
        arena = ContextLeaseArena(definition, summary_providers=providers)
        result = arena.prepare(
            ModelProfile("tiny", 4, 0),
            [
                ModuleContribution(
                    "memory",
                    (
                        PromptChunk(
                            "facts",
                            "alpha beta gamma delta epsilon",
                            required_terms=("alpha",),
                        ),
                    ),
                )
            ],
            request_id="semantic-facade-r1",
        )
        self.assertIn("alpha", result.rendered)
        self.assertTrue(result.module_plans[0].chunks[0].compressed)

    def test_donor_growth_reclaims_lease_and_compresses_borrower(self):
        arena = self.make_arena(); model = ModelProfile("char-30", 30, 0, count_mode=CountMode.EXACT)
        first = arena.prepare(model, [ModuleContribution("donor", (PromptChunk("d1", "12345"),)), ModuleContribution("borrower", (PromptChunk("b1", "abcdefghijklmnopqrst"),))], request_id="first")
        self.assertTrue(first.leases)
        second = arena.prepare(model, [ModuleContribution("donor", (PromptChunk("d2", "12345678901234567890"),)), ModuleContribution("borrower", (PromptChunk("b2", "abcdefghijklmnopqrst"),))], request_id="second")
        self.assertLessEqual(second.snapshot.modules[1].used_tokens, 10)
        self.assertTrue(any(event.event_type == "lease.reclaimed" for event in second.trace_events))
        self.assertTrue(any(event.event_type == "chunk.compressed" for event in second.trace_events))

    def test_pinned_overflow_is_rejected(self):
        arena = self.make_arena(); model = ModelProfile("char-30", 30, 0)
        with self.assertRaises(AdmissionError):
            arena.prepare(model, [ModuleContribution("donor", (PromptChunk("d", "1234567890123456789012345", protection=ProtectionPolicy.PINNED),)), ModuleContribution("borrower", ())])

    def test_unknown_module_is_rejected(self):
        arena = self.make_arena()
        with self.assertRaisesRegex(Exception, "unknown contribution"):
            arena.prepare(ModelProfile("char", 30, 0), [ModuleContribution("missing", ())])

    def test_exact_mode_requires_host_tokenizer(self):
        definition = ArenaDefinition(
            "exact-requires-tokenizer",
            (ModuleDefinition("system", 0, 8, 8, can_borrow=False),),
        )
        arena = ContextLeaseArena(definition)
        with self.assertRaisesRegex(Exception, "requires a host token counter"):
            arena.prepare(
                ModelProfile("exact", 8, 0, count_mode=CountMode.EXACT),
                [ModuleContribution("system", (PromptChunk("c", "rules"),))],
            )

    def test_duplicate_chunk_id_is_rejected(self):
        arena = self.make_arena()
        with self.assertRaisesRegex(Exception, "duplicate chunk_id"):
            arena.prepare(ModelProfile("char", 30, 0), [ModuleContribution("donor", (PromptChunk("same", "a"), PromptChunk("same", "b")))])

    def test_shared_arena_serializes_concurrent_prepare_transactions(self):
        arena = self.make_arena()
        model = ModelProfile("char-30", 30, 0, count_mode=CountMode.EXACT)

        def prepare(index):
            return arena.prepare(
                model,
                [
                    ModuleContribution("donor", (PromptChunk(f"d-{index}", "12345"),)),
                    ModuleContribution("borrower", (PromptChunk(f"b-{index}", "abcdefghijklmno"),)),
                ],
                request_id=f"concurrent-{index}",
            )

        with ThreadPoolExecutor(max_workers=6) as pool:
            results = list(pool.map(prepare, range(12)))

        self.assertEqual({result.snapshot.snapshot_seq for result in results}, set(range(1, 13)))
        event_sequences = [event.seq for result in results for event in result.trace_events]
        self.assertEqual(len(event_sequences), len(set(event_sequences)))


if __name__ == "__main__":
    unittest.main()
