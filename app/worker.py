from __future__ import annotations
import logging
import os
import random
import time
from typing import Any, Dict

from .config import settings
from .simulate.html_parse import extract_image_sources, extract_links, find_exacttarget_open_pixel
from .simulate.openers import simulate_open_via_direct, fetch_single_url
from .simulate.clickers import filter_links, choose_links, perform_clicks
from .utils.user_agents import pick_user_agent

logger = logging.getLogger(__name__)


def _headers(user_agent: str) -> dict[str, str]:
    return {
        "User-Agent": user_agent,
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Connection": "keep-alive",
    }


def process_mail(job: Dict[str, Any]) -> Dict[str, Any]:
    to_addr = job.get("to", "")
    html = job.get("html") or ""
    message_id = job.get("message_id")

    # Log job receipt for debugging with detailed HTML analysis
    html_length = len(html) if html else 0
    html_is_whitespace = html and html.strip() == "" if html else False
    html_preview_length = min(500, html_length) if html else 0
    
    logger.info("worker_job_received", extra={
        "message_id": message_id,
        "to": to_addr,
        "html_length": html_length,
        "html_is_empty": not html,
        "html_is_none": html is None,
        "html_is_whitespace": html_is_whitespace,
        "html_preview": html[:html_preview_length] if html else None,
        "html_preview_length": html_preview_length,
    })
    
    # Warn if HTML is suspiciously short or whitespace-only
    if html:
        if html_is_whitespace:
            logger.warning("worker_html_whitespace_only", extra={
                "message_id": message_id,
                "html_length": html_length,
            })
        elif html_length < 10:
            logger.warning("worker_html_very_short", extra={
                "message_id": message_id,
                "html_length": html_length,
                "html_content": html,
            })
    else:
        logger.warning("worker_html_missing", extra={
            "message_id": message_id,
            "html_is_none": html is None,
        })

    # Derive customer tag from plus addressing
    local = to_addr.split("@")[0]
    plus_tag = None
    if "+" in local:
        try:
            plus_tag = local.split("+", 1)[1]
        except Exception:
            plus_tag = None

    user_agent = pick_user_agent(settings.user_agent_pool)
    headers = _headers(user_agent)
    timeout_seconds = settings.request_timeout_ms / 1000

    # Log configuration for debugging
    logger.info("worker_config", extra={
        "message_id": message_id,
        "open_probability": settings.simulate_open_probability,
        "click_probability": settings.simulate_click_probability,
        "timeout_seconds": timeout_seconds,
    })

    # Delay before potential open
    delay_ms = random.randint(*settings.open_delay_ms)
    logger.info("worker_delay_start", extra={"message_id": message_id, "delay_ms": delay_ms})
    time.sleep(delay_ms / 1000)

    opened = False
    open_roll = random.random()
    will_attempt_open = open_roll < settings.simulate_open_probability
    
    logger.info("worker_open_roll", extra={
        "message_id": message_id,
        "roll": open_roll,
        "threshold": settings.simulate_open_probability,
        "threshold_type": type(settings.simulate_open_probability).__name__,
        "will_attempt_open": will_attempt_open,
        "comparison": f"{open_roll} < {settings.simulate_open_probability} = {will_attempt_open}",
    })
    
    if will_attempt_open:
        logger.info("worker_open_attempt_starting", extra={
            "message_id": message_id,
            "reason": "probability_check_passed",
        })
        # Log HTML content before parsing
        logger.info("worker_html_before_parsing", extra={
            "message_id": message_id,
            "html_length": html_length,
            "html_preview": html[:500] if html else None,
            "html_is_whitespace": html_is_whitespace,
        })
        
        # Always prioritize ExactTarget/SFMC open pixel when present
        special_pixel = find_exacttarget_open_pixel(html)
        images = extract_image_sources(html)
        
        logger.info("worker_open_analysis", extra={
            "message_id": message_id,
            "special_pixel_found": special_pixel is not None,
            "special_pixel_url": special_pixel[:100] if special_pixel else None,
            "total_images_found": len(images),
            "image_urls_preview": [img[:80] for img in images[:5]],  # First 5, truncated
            "html_length_processed": html_length,
        })
        
        if len(images) == 0 and not special_pixel and html:
            logger.warning("worker_no_images_found", extra={
                "message_id": message_id,
                "html_length": html_length,
                "html_preview": html[:200] if html else None,
            })
        
        # Initialize pixel_result before use
        pixel_result = None
        if special_pixel:
            logger.info("worker_pixel_fetch_starting", extra={
                "message_id": message_id,
                "url": special_pixel,
                "url_length": len(special_pixel),
            })
            pixel_result = fetch_single_url(special_pixel, headers, timeout_seconds)
            logger.info("worker_pixel_fetch", extra={
                "message_id": message_id,
                "url": special_pixel,
                "url_truncated": special_pixel[:100],
                "success": pixel_result,
                "will_set_opened": pixel_result is True,
            })
            if pixel_result:
                opened = True
                logger.info("worker_pixel_fetch_success_set_opened", extra={
                    "message_id": message_id,
                    "opened": opened,
                })
            else:
                logger.warning("worker_pixel_fetch_failed", extra={
                    "message_id": message_id,
                    "url": special_pixel,
                    "opened_remains": opened,
                })
        else:
            logger.info("worker_no_special_pixel", extra={
                "message_id": message_id,
                "reason": "special_pixel_not_found_in_html",
            })
        
        if special_pixel and special_pixel in images:
            images = [u for u in images if u != special_pixel]
        
        open_result = simulate_open_via_direct(images, headers, timeout_seconds)
        logger.info("worker_open_result", extra={
            "message_id": message_id,
            "images_fetched": len(images),
            "open_result": open_result,
        })
        opened = open_result or opened
        
        # Log final opened status and source
        opened_source = "none"
        if special_pixel and pixel_result:
            opened_source = "special_pixel"
        elif open_result:
            opened_source = "regular_images"
        
        logger.info("worker_open_final_status", extra={
            "message_id": message_id,
            "opened": opened,
            "opened_source": opened_source,
            "special_pixel_found": special_pixel is not None,
            "special_pixel_fetch_success": pixel_result if special_pixel else None,
            "regular_images_fetch_success": open_result,
        })
    else:
        logger.info("worker_open_skipped", extra={
            "message_id": message_id,
            "reason": "probability_check_failed",
            "roll": open_roll,
            "threshold": settings.simulate_open_probability,
        })
        # Warn if probability is 1.0 but we're skipping
        if settings.simulate_open_probability >= 1.0:
            logger.warning("worker_open_skipped_despite_100_percent", extra={
                "message_id": message_id,
                "roll": open_roll,
                "threshold": settings.simulate_open_probability,
                "comparison_result": open_roll < settings.simulate_open_probability,
            })

    clicks = 0
    click_roll = random.random()
    logger.info("worker_click_roll", extra={
        "message_id": message_id,
        "roll": click_roll,
        "threshold": settings.simulate_click_probability,
        "will_attempt_click": click_roll < settings.simulate_click_probability,
    })
    
    if click_roll < settings.simulate_click_probability:
        # Log HTML content before link extraction
        logger.info("worker_html_before_link_extraction", extra={
            "message_id": message_id,
            "html_length": html_length,
            "html_preview": html[:500] if html else None,
        })
        
        links = extract_links(html)
        filtered_links = filter_links(links, settings.allow_domains, settings.deny_domains)
        chosen = choose_links(filtered_links, settings.max_clicks)
        
        logger.info("worker_click_analysis", extra={
            "message_id": message_id,
            "total_links_found": len(links),
            "links_after_filter": len(filtered_links),
            "links_chosen": len(chosen),
            "chosen_urls": [link[:80] for link in chosen],
            "allow_domains": settings.allow_domains,
            "deny_domains": settings.deny_domains,
            "html_length_processed": html_length,
        })
        
        if len(links) == 0 and html:
            logger.warning("worker_no_links_found", extra={
                "message_id": message_id,
                "html_length": html_length,
                "html_preview": html[:200] if html else None,
            })
        
        clicks = perform_clicks(chosen, headers, timeout_seconds, settings.click_delay_ms)

    outcome = {
        "message_id": message_id,
        "to": to_addr,
        "customer_tag": plus_tag,
        "opened": opened,
        "clicked": clicks,
    }
    logger.info("email_simulation_complete", extra=outcome)
    return outcome
