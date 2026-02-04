from __future__ import annotations
import logging
import random
import time
from typing import Iterable, List, Optional

import httpx

from .html_parse import LinkWithRate

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


def filter_links_with_rates(
    links: List[LinkWithRate], 
    allow: Optional[list[str]], 
    deny: Optional[list[str]]
) -> List[LinkWithRate]:
    """Filter links by domain allow/deny lists, preserving LinkWithRate objects.
    
    Args:
        links: List of LinkWithRate objects to filter
        allow: Optional list of allowed domains
        deny: Optional list of denied domains
        
    Returns:
        Filtered list of LinkWithRate objects
    """
    result: List[LinkWithRate] = []
    for link in links:
        host = _domain(link.url).lower()
        if deny and any(d.lower() in host for d in deny):
            continue
        if allow and not any(a.lower() in host for a in allow):
            continue
        result.append(link)
    return result


def choose_links_weighted(
    links: List[LinkWithRate], 
    max_clicks: int, 
    global_rate: float
) -> List[str]:
    """Choose links using weighted random selection based on click rates.
    
    Each link's effective click rate is either its individual data-click-rate
    or the global_rate if not specified. Links with higher rates are selected
    more frequently.
    
    Args:
        links: List of LinkWithRate objects
        max_clicks: Maximum number of links to select
        global_rate: Global click rate to use for links without individual rates
        
    Returns:
        List of selected URLs (strings)
    """
    if max_clicks <= 0 or not links:
        return []
    
    # Calculate effective rates and weights for each link
    effective_rates = []
    link_urls = []
    
    for link in links:
        effective_rate = link.click_rate if link.click_rate is not None else global_rate
        effective_rates.append(effective_rate)
        link_urls.append(link.url)
    
    # Calculate weights: use the effective rates directly as weights
    # Links with higher rates will be selected more often
    weights = effective_rates
    
    # Check if all weights are zero
    if all(w == 0.0 for w in weights):
        logger.warning("choose_links_weighted_all_zero_weights", extra={
            "total_links": len(links),
        })
        return []
    
    # Use random.choices() for weighted selection
    # k=max_clicks allows selecting the same link multiple times if it has high weight
    chosen = random.choices(link_urls, weights=weights, k=max_clicks)
    
    logger.info("choose_links_weighted_complete", extra={
        "total_links": len(links),
        "max_clicks": max_clicks,
        "chosen_count": len(chosen),
        "effective_rates": effective_rates,
        "chosen_urls": [url[:80] for url in chosen],
    })
    
    return chosen


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
