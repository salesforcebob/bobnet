from redis import Redis
from rq import Queue
from .config import settings
import ssl


_redis: Redis | None = None
_queue: Queue | None = None


def get_redis() -> Redis:
    """
    Create a Redis connection from the configured URL.
    
    Supports both SSL (rediss://) and non-SSL (redis://) URLs.
    For SSL connections, respects REDIS_SSL_CERT_REQS setting:
    - 'required': Verify server certificate (default for production)
    - 'none': Skip certificate verification (for self-signed certs)
    """
    global _redis
    if _redis is None:
        url = settings.redis_url
        
        # Check if SSL is needed (rediss:// scheme)
        if url.startswith("rediss://"):
            cert_mode = (settings.redis_ssl_cert_reqs or "none").lower()
            
            # Create SSL context for redis-py 5.x compatibility
            ssl_context = ssl.create_default_context()
            if cert_mode != "required":
                # Skip certificate verification (for self-signed certs)
                ssl_context.check_hostname = False
                ssl_context.verify_mode = ssl.CERT_NONE
            
            _redis = Redis.from_url(url, ssl=ssl_context)
        else:
            # Non-SSL connection
            _redis = Redis.from_url(url)
    return _redis


def get_queue() -> Queue:
    global _queue
    if _queue is None:
        _queue = Queue("email_simulator", connection=get_redis())
    return _queue
