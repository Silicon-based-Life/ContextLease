from __future__ import annotations

import json
import os
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from contextlease.config import (
    arena_from_dict,
    load_json_config,
    model_from_dict,
    providers_from_dict,
)
from contextlease.errors import ConfigurationError, ProviderError
from contextlease.layout import compile_layout
from contextlease.providers import (
    CallableSummaryProvider,
    OpenAICompatibleSummaryProvider,
    SummaryProviderRegistry,
    SummaryRequest,
)


class ProviderHandler(BaseHTTPRequestHandler):
    received_auth = None
    received_payload = None

    def log_message(self, format, *args):
        return

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        type(self).received_auth = self.headers.get("Authorization")
        type(self).received_payload = json.loads(self.rfile.read(length))
        body = json.dumps({"choices": [{"message": {"content": "blue lighthouse unresolved"}}], "usage": {"prompt_tokens": 12, "completion_tokens": 3}}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class ProviderTests(unittest.TestCase):
    def test_openai_compatible_provider_uses_environment_key(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), ProviderHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        os.environ["CONTEXTLEASE_TEST_KEY"] = "unit-secret"
        try:
            provider = OpenAICompatibleSummaryProvider("mock-http", "model-a", f"http://127.0.0.1:{server.server_address[1]}/v1", api_key_env="CONTEXTLEASE_TEST_KEY")
            response = provider.summarize(SummaryRequest("source", 8, "compress", ("blue lighthouse",)))
            self.assertEqual(response.text, "blue lighthouse unresolved")
            self.assertEqual(response.output_tokens, 3)
            self.assertEqual(ProviderHandler.received_auth, "Bearer unit-secret")
            self.assertNotIn("unit-secret", json.dumps(ProviderHandler.received_payload))
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
            os.environ.pop("CONTEXTLEASE_TEST_KEY", None)

    def test_missing_environment_key_fails(self):
        provider = OpenAICompatibleSummaryProvider("missing", "m", "http://localhost:1/v1", api_key_env="MISSING_CONTEXTLEASE_KEY")
        with self.assertRaisesRegex(ProviderError, "not set"):
            provider.summarize(SummaryRequest("x", 2, "compress"))

    def test_remote_http_requires_explicit_override(self):
        with self.assertRaisesRegex(ConfigurationError, "must use https"):
            OpenAICompatibleSummaryProvider("bad", "m", "http://example.com/v1")

    def test_registry_rejects_duplicates(self):
        provider = CallableSummaryProvider("same", "m", lambda request: "x")
        registry = SummaryProviderRegistry([provider])
        with self.assertRaisesRegex(ConfigurationError, "already registered"):
            registry.register(provider)


class ConfigTests(unittest.TestCase):
    def test_inline_secret_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"
            path.write_text(json.dumps({"providers": {"x": {"api_key": "secret"}}}), encoding="utf-8")
            with self.assertRaisesRegex(ConfigurationError, "inline secrets"):
                load_json_config(path)

    def test_config_builds_arena_model_and_provider(self):
        arena = arena_from_dict({"arena_id": "a", "modules": [{"module_id": "m", "floor_tokens": 1, "target_tokens": 2, "max_tokens": 3, "reclaim_pipeline": [{"algorithm_id": "builtin.text.boundary_truncate.v1"}]}]})
        model = model_from_dict({"model_profile_id": "model", "context_limit_tokens": 10, "reserved_output_tokens": 2})
        providers = providers_from_dict({"summary": {"type": "openai-compatible", "model": "m", "base_url": "http://localhost:9999/v1"}})
        self.assertEqual(compile_layout(arena).definition.arena_id, "a")
        self.assertEqual(model.input_budget_tokens, 8)
        self.assertEqual(providers.ids(), ("summary",))

    def test_unknown_provider_type_is_rejected(self):
        with self.assertRaisesRegex(ConfigurationError, "unknown summary provider"):
            providers_from_dict({"x": {"type": "unknown", "model": "m"}})


if __name__ == "__main__":
    unittest.main()
