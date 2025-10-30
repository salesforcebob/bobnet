import os
import random
from typing import Optional, List


_DEFAULT_UAS: List[str] = [
    # Common desktop
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    # Mobile
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Linux; Android 14; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Mobile Safari/537.36",
]


def pick_user_agent(pool: Optional[list[str]] = None) -> str:
    if pool:
        return random.choice(pool)
    env_pool = os.getenv("USER_AGENT_POOL")
    if env_pool:
        candidates = [s.strip() for s in env_pool.split(",") if s.strip()]
        if candidates:
            return random.choice(candidates)
    return random.choice(_DEFAULT_UAS)
