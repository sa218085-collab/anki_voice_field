from __future__ import annotations

import json
import unittest
import urllib.error
import urllib.request

from control_server import ControlHTTPError, start_json_control_server


class ControlServerTests(unittest.TestCase):
    def setUp(self) -> None:
        def handler(request):  # type: ignore[no-untyped-def]
            if request.path == "/echo":
                return {"body": request.body}
            raise ControlHTTPError(404, "Unknown command.")

        self.server, self.thread = start_json_control_server("127.0.0.1", 0, handler)
        host, port = self.server.server_address
        self.base_url = f"http://{host}:{port}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=1)

    def test_valid_json_object_is_returned(self) -> None:
        request = urllib.request.Request(
            f"{self.base_url}/echo",
            data=json.dumps({"value": 4}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=1) as response:
            payload = json.loads(response.read().decode("utf-8"))
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["body"], {"value": 4})

    def test_invalid_json_is_rejected(self) -> None:
        request = urllib.request.Request(
            f"{self.base_url}/echo",
            data=b"[not-json",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with self.assertRaises(urllib.error.HTTPError) as raised:
            urllib.request.urlopen(request, timeout=1)
        self.assertEqual(raised.exception.code, 400)

    def test_unknown_route_is_404(self) -> None:
        with self.assertRaises(urllib.error.HTTPError) as raised:
            urllib.request.urlopen(f"{self.base_url}/missing", timeout=1)
        self.assertEqual(raised.exception.code, 404)


if __name__ == "__main__":
    unittest.main()
