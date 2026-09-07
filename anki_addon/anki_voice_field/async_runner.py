from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import Future
from typing import Any


class BackgroundRunner:
    """Route every helper HTTP call through Anki's non-collection executor."""

    def __init__(self, taskman: Any) -> None:
        self.taskman = taskman

    def submit(
        self,
        task: Callable[[], Any],
        on_done: Callable[[Future], None],
    ) -> Future:
        return self.taskman.run_in_background(
            task,
            on_done,
            uses_collection=False,
        )
