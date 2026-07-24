from __future__ import annotations

import json
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from contextlease.debug import DebugServer
from contextlease.errors import ConfigurationError
from contextlease.models import (
    ArenaDefinition,
    CompressionStepSpec,
    ModelProfile,
    ModuleContribution,
    ModuleDefinition,
    PromptChunk,
)
from contextlease.observation import ObservationStore
from contextlease.runtime import ContextLeaseArena


def prepared_arena(store=None):
    definition = ArenaDefinition("debug-test", (ModuleDefinition("memory", 1, 10, 20, reclaim_pipeline=(CompressionStepSpec("builtin.text.boundary_truncate.v1"),)),))
    arena = ContextLeaseArena(definition, observations=store, instance_id="debug-instance")
    arena.prepare(ModelProfile("debug-model", 30, 5), [ModuleContribution("memory", (PromptChunk("secret-chunk", "PRIVATE PROMPT BODY"),))], request_id="debug-request")
    return arena


class ObservationTests(unittest.TestCase):
    def test_ring_buffer_is_bounded_and_reports_drops(self):
        store = ObservationStore(max_events_per_arena=2)
        prepared_arena(store)
        snapshot = store.get_snapshot("debug-test")
        self.assertIsNotNone(snapshot)
        self.assertGreater(snapshot.health["events_dropped"], 0)
        self.assertLessEqual(len(store.events_after("debug-test", 0)), 2)

    def test_event_sequences_are_monotonic(self):
        arena = prepared_arena()
        events = arena.observations.events_after("debug-test", 0)
        self.assertEqual([event.seq for event in events], sorted(event.seq for event in events))
        self.assertEqual(len({event.event_id for event in events}), len(events))


class DebugServerTests(unittest.TestCase):
    def setUp(self):
        self.arena = prepared_arena()
        self.server = DebugServer(self.arena.observations, port=0).start()

    def tearDown(self):
        self.server.stop()

    def get(self, path):
        with urlopen(f"{self.server.url}{path}", timeout=4) as response:
            return response.status, dict(response.headers), response.read().decode("utf-8")

    def test_health_and_arena_list(self):
        status, _, health = self.get("/api/v1/health")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(health)["status"], "ok")
        _, _, arenas = self.get("/api/v1/arenas")
        self.assertEqual(json.loads(arenas)["items"][0]["arena_id"], "debug-test")

    def test_snapshot_has_no_prompt_body(self):
        _, _, body = self.get("/api/v1/arenas/debug-test/snapshot")
        self.assertNotIn("PRIVATE PROMPT BODY", body)
        self.assertEqual(json.loads(body)["request_id"], "debug-request")

    def test_modules_leases_and_events_endpoints(self):
        for path in ("modules", "leases", "events"):
            status, _, body = self.get(f"/api/v1/arenas/debug-test/{path}")
            self.assertEqual(status, 200)
            self.assertIn("items", json.loads(body))

    def test_static_page_has_security_headers(self):
        status, headers, body = self.get("/")
        self.assertEqual(status, 200)
        self.assertIn("ContextLease", body)
        self.assertEqual(headers.get("X-Content-Type-Options"), "nosniff")
        for path, expected_type in (("/app.css", "text/css"), ("/app.js", "text/javascript")):
            asset_status, asset_headers, _ = self.get(path)
            self.assertEqual(asset_status, 200)
            self.assertEqual(asset_headers["Content-Type"].split(";", 1)[0], expected_type)

    def test_sse_starts_with_existing_event(self):
        with urlopen(f"{self.server.url}/api/v1/arenas/debug-test/stream", timeout=4) as response:
            lines = [response.readline().decode("utf-8").strip() for _ in range(3)]
        self.assertTrue(any(line.startswith("id: ") for line in lines))
        self.assertTrue(any(line.startswith("event: ") for line in lines))

    def test_remote_binding_requires_auth(self):
        with self.assertRaises(ConfigurationError):
            DebugServer(self.arena.observations, host="0.0.0.0", port=0)

    def test_auth_token_is_enforced(self):
        server = DebugServer(self.arena.observations, port=0, auth_token="test-token").start()
        try:
            with self.assertRaises(HTTPError) as caught:
                urlopen(f"{server.url}/api/v1/health", timeout=3)
            caught.exception.close()
            request = Request(f"{server.url}/api/v1/health", headers={"Authorization": "Bearer test-token"})
            with urlopen(request, timeout=3) as response:
                self.assertEqual(response.status, 200)
        finally:
            server.stop()


if __name__ == "__main__":
    unittest.main()
