from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stderr, redirect_stdout
from importlib import resources
from pathlib import Path

from contextlease.cli import main


DEMO = Path(__file__).parents[1] / "examples" / "demo.json"


class CliTests(unittest.TestCase):
    def test_bundled_demo_and_schema_are_valid_json(self):
        demo = resources.files("contextlease.examples").joinpath("demo.json")
        schema = resources.files("contextlease.schema").joinpath("contextlease.schema.json")
        self.assertEqual(json.loads(demo.read_text(encoding="utf-8"))["arena"]["arena_id"], "agent-demo")
        self.assertEqual(
            json.loads(schema.read_text(encoding="utf-8"))["$schema"],
            "https://json-schema.org/draft/2020-12/schema",
        )

    def test_validate_command(self):
        output = io.StringIO()
        with redirect_stdout(output):
            code = main(["validate", str(DEMO)])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output.getvalue())["status"], "valid")

    def test_version_uses_package_metadata(self):
        output = io.StringIO()
        with self.assertRaises(SystemExit) as exit_context, redirect_stdout(output):
            main(["--version"])
        self.assertEqual(exit_context.exception.code, 0)
        self.assertEqual(output.getvalue().strip(), "contextlease 0.2.0")

    def test_prepare_hides_content_by_default(self):
        output = io.StringIO()
        with redirect_stdout(output):
            code = main(["prepare", str(DEMO), "--request-id", "cli-test"])
        payload = json.loads(output.getvalue())
        self.assertEqual(code, 0); self.assertEqual(payload["request_id"], "cli-test")
        self.assertIn("hidden", payload["rendered"])

    def test_invalid_config_returns_nonzero(self):
        error = io.StringIO()
        with redirect_stderr(error):
            code = main(["validate", "missing.json"])
        self.assertEqual(code, 2); self.assertIn("error", error.getvalue())


if __name__ == "__main__":
    unittest.main()
