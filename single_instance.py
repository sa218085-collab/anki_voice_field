from __future__ import annotations

import socket

import config


def acquire_instance_lock() -> socket.socket:
    lock_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    try:
        lock_socket.bind(("127.0.0.1", config.INSTANCE_LOCK_PORT))
        lock_socket.listen(1)
    except OSError as exc:
        lock_socket.close()
        raise RuntimeError(
            "Anki Voice Field already appears to be running. "
            "Use the existing helper window, or close it before starting another one."
        ) from exc

    return lock_socket
