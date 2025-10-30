from __future__ import annotations
from rq import Worker, Queue
from rq.connections import Connection
from .queue import get_redis


def main() -> None:
    # Ensure the worker uses our configured Redis connection (with SSL behavior)
    with Connection(get_redis()):
        worker = Worker(["email_simulator"])
        # Enable scheduler to support delayed jobs (future-proofing)
        worker.work(with_scheduler=True)


if __name__ == "__main__":
    main()
