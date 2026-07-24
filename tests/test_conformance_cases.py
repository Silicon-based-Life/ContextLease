from __future__ import annotations

import json
import unittest
from pathlib import Path

from contextlease.native import NativeArena

CASES_PATH = Path(__file__).parents[1] / "spec" / "conformance" / "runtime-cases.json"


class SharedRuntimeConformanceTests(unittest.TestCase):
    def test_runtime_cases(self) -> None:
        cases = json.loads(CASES_PATH.read_text(encoding="utf-8"))["cases"]
        self.assertGreaterEqual(len(cases), 8)
        for case in cases:
            with self.subTest(case=case["name"]):
                with NativeArena(case["definition"]) as arena:
                    prepared = arena.prepare(case["request"])
                expected = case["assert"]
                self.assertLessEqual(
                    prepared["prompt_tokens"],
                    expected["max_prompt_tokens"],
                )
                if "input_budget_tokens" in expected:
                    self.assertEqual(
                        expected["input_budget_tokens"],
                        prepared["input_budget_tokens"],
                    )
                for term in expected.get("must_contain", []):
                    self.assertIn(term, prepared["rendered"])
                module_ids = [item["module_id"] for item in prepared["module_plans"]]
                self.assertEqual(expected.get("expected_modules", module_ids), module_ids)
                borrower = expected.get("lease_borrower")
                if borrower:
                    self.assertTrue(
                        any(lease["borrower_module_id"] == borrower for lease in prepared["leases"])
                    )
                positions = [
                    prepared["rendered"].index(value)
                    for value in expected.get("render_order", [])
                ]
                self.assertEqual(sorted(positions), positions)


if __name__ == "__main__":
    unittest.main()
