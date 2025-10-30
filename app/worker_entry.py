from __future__ import annotations
from rq import Worker
from .queue import get_redis


def main() -> None:
    # Use explicit connection to avoid reliance on Connection context manager
    worker = Worker(["email_simulator"], connection=get_redis())
    worker.work(with_scheduler=True)


if __name__ == "__main__":
    main()
