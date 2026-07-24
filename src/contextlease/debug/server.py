from __future__ import annotations

import hmac
import json
import sys
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from ..errors import ConfigurationError
from ..models import to_public_dict
from ..observation import ObservationStore

_LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}
_STATIC_CONTENT_TYPES = {
    "index.html": "text/html",
    "app.css": "text/css",
    "app.js": "text/javascript",
}


class DebugRequestHandler(BaseHTTPRequestHandler):
    server_version = "ContextLeaseDebug/0.1"

    @property
    def observation_store(self) -> ObservationStore:
        return self.server.observation_store  # type: ignore[attr-defined]

    @property
    def auth_token(self) -> str | None:
        return self.server.auth_token  # type: ignore[attr-defined]

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _authorized(self) -> bool:
        if not self.auth_token:
            return True
        expected = f"Bearer {self.auth_token}"
        supplied = self.headers.get("Authorization", "")
        return hmac.compare_digest(expected, supplied)

    def _send_json(self, status: int, payload: Any) -> None:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; connect-src 'self'; style-src 'self'; script-src 'self'")
        self.end_headers()
        self.wfile.write(body)

    def _serve_static(self, name: str) -> None:
        safe_name = name if name in _STATIC_CONTENT_TYPES else "index.html"
        asset = resources.files("contextlease.debug.static").joinpath(safe_name)
        try:
            body = asset.read_bytes()
        except (FileNotFoundError, OSError):
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "asset_not_found"})
            return
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", f"{_STATIC_CONTENT_TYPES[safe_name]}; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path in {"/", "/index.html", "/app.css", "/app.js"}:
            self._serve_static(parsed.path.lstrip("/") or "index.html")
            return
        if not parsed.path.startswith("/api/v1/"):
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
            return
        if not self._authorized():
            self._send_json(HTTPStatus.UNAUTHORIZED, {"error": "unauthorized"})
            return
        if parsed.path == "/api/v1/health":
            self._send_json(HTTPStatus.OK, {"status": "ok", "schema_version": "1.0"})
            return
        if parsed.path == "/api/v1/arenas":
            self._send_json(HTTPStatus.OK, {"schema_version": "1.0", "items": self.observation_store.list_arenas()})
            return

        parts = [unquote(part) for part in parsed.path.split("/") if part]
        if len(parts) < 4 or parts[:3] != ["api", "v1", "arenas"]:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
            return
        arena_id = parts[3]
        snapshot = self.observation_store.get_snapshot(arena_id)
        if snapshot is None:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "arena_not_found", "arena_id": arena_id})
            return
        if len(parts) == 5 and parts[4] == "snapshot":
            self._send_json(HTTPStatus.OK, snapshot.public_dict())
        elif len(parts) == 5 and parts[4] == "modules":
            self._send_json(HTTPStatus.OK, {"schema_version": "1.0", "items": to_public_dict(snapshot.modules)})
        elif len(parts) == 5 and parts[4] == "leases":
            self._send_json(HTTPStatus.OK, {"schema_version": "1.0", "items": to_public_dict(snapshot.leases)})
        elif len(parts) == 5 and parts[4] == "events":
            query = parse_qs(parsed.query)
            after_seq = int(query.get("after_seq", ["0"])[0])
            limit = int(query.get("limit", ["1000"])[0])
            events = self.observation_store.events_after(arena_id, after_seq, limit)
            minimum = self.observation_store.minimum_event_seq(arena_id)
            reset_required = minimum is not None and after_seq not in {0, minimum - 1} and after_seq < minimum
            self._send_json(
                HTTPStatus.OK,
                {
                    "schema_version": "1.0",
                    "reset_required": reset_required,
                    "minimum_seq": minimum,
                    "items": to_public_dict(events),
                },
            )
        elif len(parts) == 5 and parts[4] == "stream":
            self._serve_stream(arena_id)
        elif len(parts) == 6 and parts[4] == "requests":
            request_id = parts[5]
            events = [
                event
                for event in self.observation_store.events_after(arena_id, 0, 10_000)
                if event.request_id == request_id
            ]
            if not events:
                self._send_json(HTTPStatus.GONE, {"error": "request_expired", "request_id": request_id})
            else:
                self._send_json(
                    HTTPStatus.OK,
                    {"schema_version": "1.0", "request_id": request_id, "events": to_public_dict(events)},
                )
        else:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "not_found"})

    def _serve_stream(self, arena_id: str) -> None:
        try:
            after_seq = int(self.headers.get("Last-Event-ID", "0") or "0")
        except ValueError:
            after_seq = 0
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()
        try:
            while not self.server.shutdown_event.is_set():  # type: ignore[attr-defined]
                events = self.observation_store.wait_for_events(arena_id, after_seq, timeout=10.0)
                if not events:
                    self.wfile.write(b": keepalive\n\n")
                    self.wfile.flush()
                    continue
                for event in events:
                    data = json.dumps(to_public_dict(event), ensure_ascii=False, separators=(",", ":"))
                    payload = f"id: {event.seq}\nevent: {event.event_type}\ndata: {data}\n\n".encode("utf-8")
                    self.wfile.write(payload)
                    self.wfile.flush()
                    after_seq = event.seq
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, TimeoutError):
            return


class DebugHTTPServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address: tuple[str, int], store: ObservationStore, auth_token: str | None) -> None:
        super().__init__(address, DebugRequestHandler)
        self.observation_store = store
        self.auth_token = auth_token
        self.shutdown_event = threading.Event()

    def handle_error(self, request: Any, client_address: Any) -> None:
        error = sys.exc_info()[1]
        if isinstance(error, (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, TimeoutError)):
            return
        super().handle_error(request, client_address)


class DebugServer:
    def __init__(
        self,
        store: ObservationStore,
        host: str = "127.0.0.1",
        port: int = 0,
        *,
        auth_token: str | None = None,
    ) -> None:
        if host not in _LOOPBACK_HOSTS and not auth_token:
            raise ConfigurationError("non-loopback Debug Web binding requires auth_token")
        self._server = DebugHTTPServer((host, port), store, auth_token)
        self._thread: threading.Thread | None = None

    @property
    def host(self) -> str:
        return str(self._server.server_address[0])

    @property
    def port(self) -> int:
        return int(self._server.server_address[1])

    @property
    def url(self) -> str:
        host = "127.0.0.1" if self.host in {"0.0.0.0", "::"} else self.host
        return f"http://{host}:{self.port}"

    def start(self) -> "DebugServer":
        if self._thread and self._thread.is_alive():
            return self
        self._thread = threading.Thread(target=self._server.serve_forever, name="contextlease-debug", daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        self._server.shutdown_event.set()
        self._server.shutdown()
        self._server.server_close()
        if self._thread:
            self._thread.join(timeout=5)

    def __enter__(self) -> "DebugServer":
        return self.start()

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        self.stop()
