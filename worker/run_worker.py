from __future__ import annotations

import asyncio

from arq.worker import run_worker

from .arq_worker import WorkerSettings


def _ensure_event_loop() -> None:
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        # Python 3.14 no longer creates an implicit loop for the main thread.
        asyncio.set_event_loop(asyncio.new_event_loop())


def main() -> None:
    _ensure_event_loop()
    run_worker(WorkerSettings)


if __name__ == "__main__":
    main()
