from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from typing import Callable, Any


ControlCallback = Callable[[], dict[str, Any]]


def start_control_server(
    host: str,
    port: int,
    *,
    on_toggle: ControlCallback,
    on_show: ControlCallback,
    on_test_anki: ControlCallback,
) -> tuple[ThreadingHTTPServer, Thread]:
    routes: dict[str, ControlCallback] = {
        "/health": lambda: {"ok": True, "message": "Anki Voice Field helper is running."},
        "/toggle": on_toggle,
        "/show": on_show,
        "/test-anki": on_test_anki,
    }

    class ControlRequestHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self._handle_request()

        def do_POST(self) -> None:
            self._handle_request()

        def log_message(self, format: str, *args: object) -> None:
            return

        def _handle_request(self) -> None:
            content_length = int(self.headers.get("Content-Length", "0") or "0")
            if content_length:
                self.rfile.read(content_length)

            callback = routes.get(self.path)
            if callback is None:
                self._write_json(404, {"ok": False, "error": "Unknown command."})
                return

            try:
                payload = callback()
            except Exception as exc:
                self._write_json(500, {"ok": False, "error": str(exc)})
                return

            self._write_json(200, {"ok": True, **payload})

        def _write_json(self, status_code: int, payload: dict[str, Any]) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status_code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer((host, port), ControlRequestHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread
