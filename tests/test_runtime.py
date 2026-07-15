from __future__ import annotations

import unittest
from concurrent.futures import ThreadPoolExecutor

from contextlease.enums import CountMode, ProtectionPolicy
from contextlease.errors import AdmissionError
from contextlease.models import ArenaDefinition, CompressionStepSpec, ModelProfile, ModuleContribution, ModuleDefinition, PromptChunk
from contextlease.runtime import ContextLeaseArena
from contextlease.tokenization import CharacterTokenCounter


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
