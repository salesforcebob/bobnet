from __future__ import annotations
import logging
from typing import List
import httpx

logger = logging.getLogger(__name__)


def simulate_open_via_direct(image_urls: List[str], headers: dict, timeout_seconds: float) -> bool:
    if not image_urls:
        return False
    opened = False
    with httpx.Client(timeout=timeout_seconds, follow_redirects=True, headers=headers) as client:
        for url in image_urls[:5]:  # cap to avoid flooding
            try:
                resp = client.get(url)
                logger.info("open_fetch", extra={"url": url, "status": resp.status_code})
                if 200 <= resp.status_code < 400:
                    opened = True
            except Exception as e:
                logger.warning("open_fetch_error", extra={"url": url, "error": str(e)})
    return opened
