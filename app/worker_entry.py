from __future__ import annotations
from rq import Worker
from .queue import get_redis
from .logging import configure_json_logging


def main() -> None:
    # Configure JSON logging for worker process
    configure_json_logging()
    
    # Use explicit connection to avoid reliance on Connection context manager
    worker = Worker(["email_simulator"], connection=get_redis())
    worker.work(with_scheduler=True)


if __name__ == "__main__":
    main()
