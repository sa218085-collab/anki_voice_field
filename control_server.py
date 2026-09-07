from __future__ import annotations

import json
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from typing import Any, Callable
from urllib.parse import parse_qs, urlsplit


MAX_REQUEST_BYTES = 1_000_000


@dataclass(frozen=True)
class ControlRequest:
    method: str
    path: str
    query: dict[str, list[str]]
    body: dict[str, Any]


class ControlHTTPError(RuntimeError):
    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code


JSONHandler = Callable[[ControlRequest], dict[str, Any]]
ControlCallback = Callable[[], dict[str, Any]]


def start_json_control_server(
    host: str,
    port: int,
    handler: JSONHandler,
) -> tuple[ThreadingHTTPServer, Thread]:
    class ControlRequestHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self._handle_request()

        def do_POST(self) -> None:
            self._handle_request()

        def log_message(self, format: str, *args: object) -> None:
            return

        def _handle_request(self) -> None:
            try:
                body = self._read_json_body()
                parsed = urlsplit(self.path)
                payload = handler(
                    ControlRequest(
                        method=self.command,
                        path=parsed.path,
                        query=parse_qs(parsed.query, keep_blank_values=True),
                        body=body,
                    )
                )
            except ControlHTTPError as exc:
                self._write_json(
                    exc.status_code,
                    {"ok": False, "error": str(exc)},
                )
                return
            except Exception as exc:
                self._write_json(500, {"ok": False, "error": str(exc)})
                return

            self._write_json(200, {"ok": True, **payload})

        def _read_json_body(self) -> dict[str, Any]:
            raw_length = self.headers.get("Content-Length", "0") or "0"
            try:
                content_length = int(raw_length)
            except ValueError as exc:
                raise ControlHTTPError(400, "Invalid Content-Length header.") from exc

            if content_length < 0 or content_length > MAX_REQUEST_BYTES:
                raise ControlHTTPError(413, "Request body is too large.")
            if not content_length:
                return {}

            try:
                payload = json.loads(self.rfile.read(content_length).decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ControlHTTPError(400, "Request body must be valid JSON.") from exc

            if not isinstance(payload, dict):
                raise ControlHTTPError(400, "Request body must be a JSON object.")
            return payload

        def _write_json(self, status_code: int, payload: dict[str, Any]) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status_code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer((host, port), ControlRequestHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def start_control_server(
    host: str,
    port: int,
    *,
    on_toggle: ControlCallback,
    on_show: ControlCallback,
    on_test_anki: ControlCallback,
) -> tuple[ThreadingHTTPServer, Thread]:
    """Start the original v1 command server used by the legacy launcher."""

    routes: dict[str, ControlCallback] = {
        "/health": lambda: {
            "message": "Anki Voice Field helper is running.",
        },
        "/toggle": on_toggle,
        "/show": on_show,
        "/test-anki": on_test_anki,
    }

    def handler(request: ControlRequest) -> dict[str, Any]:
        callback = routes.get(request.path)
        if callback is None:
            raise ControlHTTPError(404, "Unknown command.")
        return callback()

    return start_json_control_server(host, port, handler)
