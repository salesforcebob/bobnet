from redis import Redis
from rq import Queue
from .config import settings
import ssl


_redis: Redis | None = None
_queue: Queue | None = None


def get_redis() -> Redis:
    global _redis
    if _redis is None:
        cert_mode = (settings.redis_ssl_cert_reqs or "none").lower()
        cert_reqs = ssl.CERT_REQUIRED if cert_mode == "required" else ssl.CERT_NONE
        _redis = Redis.from_url(settings.redis_url, ssl_cert_reqs=cert_reqs)
    return _redis


def get_queue() -> Queue:
    global _queue
    if _queue is None:
        _queue = Queue("email_simulator", connection=get_redis())
    return _queue
