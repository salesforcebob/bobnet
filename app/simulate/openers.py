from __future__ import annotations
import logging
from typing import List
import httpx

logger = logging.getLogger(__name__)


def fetch_single_url(url: str, headers: dict, timeout_seconds: float) -> bool:
    logger.info("open_pixel_fetch_starting", extra={
        "url": url,
        "url_length": len(url),
        "timeout_seconds": timeout_seconds,
        "headers_keys": list(headers.keys()),
    })
    
    try:
        with httpx.Client(timeout=timeout_seconds, follow_redirects=True, headers=headers) as client:
            resp = client.get(url)
            status_code = resp.status_code
            is_success = 200 <= status_code < 400
            
            logger.info("open_pixel_fetch_complete", extra={
                "url": url,
                "status_code": status_code,
                "is_success": is_success,
                "response_headers": dict(resp.headers) if hasattr(resp, 'headers') else None,
                "content_length": len(resp.content) if hasattr(resp, 'content') else None,
            })
            
            return is_success
    except httpx.TimeoutException as e:
        logger.error("open_pixel_fetch_timeout", extra={
            "url": url,
            "timeout_seconds": timeout_seconds,
            "error": str(e),
            "error_type": type(e).__name__,
        })
        return False
    except httpx.RequestError as e:
        logger.error("open_pixel_fetch_request_error", extra={
            "url": url,
            "error": str(e),
            "error_type": type(e).__name__,
        })
        return False
    except Exception as e:
        logger.error("open_pixel_fetch_error", extra={
            "url": url,
            "error": str(e),
            "error_type": type(e).__name__,
            "error_repr": repr(e),
        })
        return False


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
