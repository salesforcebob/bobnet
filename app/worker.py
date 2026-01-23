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

    # Log job receipt for debugging
    logger.info("worker_job_received", extra={
        "message_id": message_id,
        "to": to_addr,
        "html_length": len(html) if html else 0,
        "html_is_empty": not html,
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
    logger.info("worker_open_roll", extra={
        "message_id": message_id,
        "roll": open_roll,
        "threshold": settings.simulate_open_probability,
        "will_attempt_open": open_roll < settings.simulate_open_probability,
    })
    
    if open_roll < settings.simulate_open_probability:
        # Always prioritize ExactTarget/SFMC open pixel when present
        special_pixel = find_exacttarget_open_pixel(html)
        images = extract_image_sources(html)
        
        logger.info("worker_open_analysis", extra={
            "message_id": message_id,
            "special_pixel_found": special_pixel is not None,
            "special_pixel_url": special_pixel[:100] if special_pixel else None,
            "total_images_found": len(images),
            "image_urls_preview": [img[:80] for img in images[:5]],  # First 5, truncated
        })
        
        if special_pixel:
            pixel_result = fetch_single_url(special_pixel, headers, timeout_seconds)
            logger.info("worker_pixel_fetch", extra={
                "message_id": message_id,
                "url": special_pixel[:100],
                "success": pixel_result,
            })
            if pixel_result:
                opened = True
        
        if special_pixel and special_pixel in images:
            images = [u for u in images if u != special_pixel]
        
        open_result = simulate_open_via_direct(images, headers, timeout_seconds)
        logger.info("worker_open_result", extra={
            "message_id": message_id,
            "images_fetched": len(images),
            "open_result": open_result,
        })
        opened = open_result or opened

    clicks = 0
    click_roll = random.random()
    logger.info("worker_click_roll", extra={
        "message_id": message_id,
        "roll": click_roll,
        "threshold": settings.simulate_click_probability,
        "will_attempt_click": click_roll < settings.simulate_click_probability,
    })
    
    if click_roll < settings.simulate_click_probability:
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
