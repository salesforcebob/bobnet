from __future__ import annotations
from redis import Redis


def mark_if_first(redis: Redis, key: str, ttl_seconds: int) -> bool:
    # Use SET with NX and EX for atomic set-if-not-exists with expiry
    # Returns True if set (first time), False if already exists
    result = redis.set(name=key, value=1, ex=ttl_seconds, nx=True)
    return bool(result)
