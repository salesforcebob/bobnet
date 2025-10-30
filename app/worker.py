from __future__ import annotations
import logging
import os
import random
import time
from typing import Any, Dict

from .config import settings
from .simulate.html_parse import extract_image_sources, extract_links
from .simulate.openers import simulate_open_via_direct
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

    # Delay before potential open
    time.sleep(random.randint(*settings.open_delay_ms) / 1000)

    opened = False
    if random.random() < settings.simulate_open_probability:
        images = extract_image_sources(html)
        opened = simulate_open_via_direct(images, headers, timeout_seconds)

    clicks = 0
    if random.random() < settings.simulate_click_probability:
        links = extract_links(html)
        links = filter_links(links, settings.allow_domains, settings.deny_domains)
        chosen = choose_links(links, settings.max_clicks)
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
