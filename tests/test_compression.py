from __future__ import annotations

import unittest

from contextlease.compression import (
    CompressionPipeline,
    CompressionRequest,
    create_builtin_registry,
)
from contextlease.models import CompressionStepSpec
from contextlease.providers import CallableSummaryProvider, SummaryProviderRegistry
from contextlease.tokenization import CharacterTokenCounter, RegexTokenCounter


class CompressionTests(unittest.TestCase):
    def setUp(self):
        self.registry = create_builtin_registry()
        self.regex = RegexTokenCounter()
        self.chars = CharacterTokenCounter()

    def run_algorithm(self, algorithm_id, content, target=10, *, options=None, required=(), services=None, counter=None):
        request = CompressionRequest(content, target, counter or self.regex, required_terms=required, options=options or {}, services=services or {})
        return self.registry.get(algorithm_id).compress(request)

    def test_registry_contains_twelve_deterministic_and_two_semantic_algorithms(self):
        ids = self.registry.ids()
        self.assertEqual(len(ids), 14)
        self.assertIn("builtin.semantic.summary.v1", ids)
        self.assertIn("builtin.message.group_select.v1", ids)

    def test_normalize_whitespace_preserves_fenced_code(self):
        result = self.run_algorithm("builtin.text.normalize_whitespace.v1", "a    b\n\n\n```py\nx  =  1\n```", 100)
        self.assertIn("x  =  1", result.content)
        self.assertNotIn("a    b", result.content)

    def test_deduplicate_blocks(self):
        result = self.run_algorithm("builtin.text.deduplicate_blocks.v1", "Alpha\n\nBeta\n\nalpha", 100)
        self.assertEqual(result.content, "Alpha\n\nBeta")
        self.assertEqual(len(result.removed_items), 1)

    def test_structured_minify(self):
        result = self.run_algorithm("builtin.structured.minify.v1", '{\n  "b": 2, "a": 1\n}', 100, counter=self.chars)
        self.assertEqual(result.content, '{"a":1,"b":2}')

    def test_exact_deduplicate(self):
        result = self.run_algorithm("builtin.collection.exact_deduplicate.v1", ["a", "b", "a"], 100)
        self.assertEqual(result.content, ["a", "b"])

    def test_similarity_deduplicate(self):
        result = self.run_algorithm("builtin.collection.similarity_deduplicate.v1", ["the blue lighthouse", "the blue lighthouse!", "harbor"], 100, options={"threshold": 0.85})
        self.assertEqual(len(result.content), 2)

    def test_priority_select(self):
        content = [{"content": "low long text", "priority": 1}, {"content": "critical", "priority": 10}]
        result = self.run_algorithm("builtin.collection.priority_select.v1", content, 10)
        self.assertTrue(any(item["content"] == "critical" for item in result.content))

    def test_recency_select(self):
        content = [{"content": "old old old"}, {"content": "latest"}]
        result = self.run_algorithm("builtin.collection.recency_select.v1", content, 8)
        self.assertEqual(result.content[-1]["content"], "latest")

    def test_extractive_rank_keeps_required_sentence(self):
        text = "Optional weather was cloudy. The blue lighthouse is unresolved. Old detail repeated repeated repeated."
        result = self.run_algorithm("builtin.text.extractive_sentence_rank.v1", text, 9, required=("blue lighthouse",))
        self.assertIn("blue lighthouse", result.content)

    def test_boundary_truncate_meets_target(self):
        result = self.run_algorithm("builtin.text.boundary_truncate.v1", "one two three four five six", 3)
        self.assertLessEqual(result.after_tokens, 3)

    def test_boundary_truncate_refuses_to_drop_required_term(self):
        text = "one two three required"
        result = self.run_algorithm("builtin.text.boundary_truncate.v1", text, 2, required=("required",))
        self.assertEqual(result.content, text)
        self.assertEqual(result.status, "required_terms_blocked")

    def test_field_prune_respects_protected_fields(self):
        result = self.run_algorithm("builtin.structured.field_prune.v1", {"id": "fixed", "optional": "very long detail"}, 8, options={"protected_fields": ["id"]})
        self.assertEqual(result.content["id"], "fixed")
        self.assertNotIn("optional", result.content)

    def test_message_group_select_keeps_tool_round_atomic(self):
        messages = [
            {"role": "system", "content": "rules"},
            {"role": "assistant", "content": "call", "dependency_group": "tool-1"},
            {"role": "tool", "content": "result", "dependency_group": "tool-1"},
            {"role": "user", "content": "latest"},
        ]
        result = self.run_algorithm("builtin.message.group_select.v1", messages, 20)
        roles = [item["role"] for item in result.content]
        self.assertEqual(roles.count("assistant"), roles.count("tool"))

    def test_reference_externalize(self):
        result = self.run_algorithm("builtin.reference.externalize.v1", "large payload with many repeated details that should live in an external store", 20, options={"reference_id": "doc-7"})
        self.assertEqual(result.content, "[Context reference: doc-7]")

    def test_semantic_summary_uses_configured_provider(self):
        providers = SummaryProviderRegistry([CallableSummaryProvider("mock", "mock-1", lambda req: "blue lighthouse remains unresolved")])
        result = self.run_algorithm("builtin.semantic.summary.v1", "long blue lighthouse context that should shrink", 8, options={"provider": "mock"}, required=("blue lighthouse",), services={"summary_providers": providers})
        self.assertIn("blue lighthouse", result.content)
        self.assertEqual(result.trace["provider_id"], "mock")

    def test_semantic_summary_rejects_missing_required_term(self):
        providers = SummaryProviderRegistry([CallableSummaryProvider("mock", "mock-1", lambda req: "wrong summary")])
        result = self.run_algorithm("builtin.semantic.summary.v1", "blue lighthouse source", 8, options={"provider": "mock"}, required=("blue lighthouse",), services={"summary_providers": providers})
        self.assertEqual(result.status, "required_terms_blocked")

    def test_semantic_portfolio_selects_shortest_valid_candidate(self):
        providers = SummaryProviderRegistry([
            CallableSummaryProvider("long", "m1", lambda req: "blue lighthouse remains unresolved and needs a future answer"),
            CallableSummaryProvider("short", "m2", lambda req: "blue lighthouse unresolved"),
        ])
        result = self.run_algorithm("builtin.semantic.portfolio.v1", "blue lighthouse source detail", 10, options={"providers": ["long", "short"]}, required=("blue lighthouse",), services={"summary_providers": providers})
        self.assertEqual(result.trace["selected_provider"], "short")

    def test_pipeline_is_monotonic(self):
        pipeline = CompressionPipeline(self.registry)
        result = pipeline.execute(CompressionRequest("a    b\n\na    b\n\nextra words here", 4, self.regex), [CompressionStepSpec("builtin.text.normalize_whitespace.v1"), CompressionStepSpec("builtin.text.deduplicate_blocks.v1"), CompressionStepSpec("builtin.text.boundary_truncate.v1")])
        self.assertLessEqual(result.after_tokens, result.before_tokens)
        self.assertLessEqual(result.after_tokens, 4)


if __name__ == "__main__":
    unittest.main()
