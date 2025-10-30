from __future__ import annotations
import logging
import random
import time
from typing import Iterable, List, Optional

import httpx

logger = logging.getLogger(__name__)


def _domain(url: str) -> str:
    try:
        # Avoid importing urllib to keep small; best-effort split
        return url.split("//", 1)[1].split("/", 1)[0]
    except Exception:
        return url


def filter_links(links: Iterable[str], allow: Optional[list[str]], deny: Optional[list[str]]) -> List[str]:
    result: List[str] = []
    for link in links:
        host = _domain(link).lower()
        if deny and any(d.lower() in host for d in deny):
            continue
        if allow and not any(a.lower() in host for a in allow):
            continue
        result.append(link)
    return result


def choose_links(links: List[str], max_clicks: int) -> List[str]:
    if max_clicks <= 0 or not links:
        return []
    shuffled = links[:]
    random.shuffle(shuffled)
    return shuffled[:max_clicks]


def perform_clicks(links: List[str], headers: dict, timeout_seconds: float, delay_range_ms: tuple[int, int]) -> int:
    if not links:
        return 0
    clicks = 0
    with httpx.Client(timeout=timeout_seconds, follow_redirects=True, headers=headers) as client:
        for link in links:
            delay = random.randint(*delay_range_ms) / 1000
            time.sleep(delay)
            try:
                resp = client.get(link)
                logger.info("click_fetch", extra={"url": link, "status": resp.status_code})
                if 200 <= resp.status_code < 400:
                    clicks += 1
            except Exception as e:
                logger.warning("click_fetch_error", extra={"url": link, "error": str(e)})
    return clicks
