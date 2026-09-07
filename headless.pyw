from __future__ import annotations

import config
from control_server import start_json_control_server
from single_instance import acquire_instance_lock
from voice_service import VoiceService


def main() -> None:
    try:
        instance_lock = acquire_instance_lock()
    except RuntimeError:
        # Anki will query /health and either use the existing v2 service or show
        # a protocol-mismatch message for an older helper.
        return

    service = VoiceService()
    server, thread = start_json_control_server(
        config.CONTROL_SERVER_HOST,
        config.CONTROL_SERVER_PORT,
        service.handle_request,
    )
    try:
        thread.join()
    finally:
        service.close()
        server.shutdown()
        server.server_close()
        instance_lock.close()


if __name__ == "__main__":
    main()
