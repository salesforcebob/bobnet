from __future__ import annotations
from dataclasses import dataclass
from typing import List, Optional
from bs4 import BeautifulSoup
import logging

logger = logging.getLogger(__name__)


@dataclass
class LinkWithRate:
    """Represents a link URL with an optional per-link click rate."""
    url: str
    click_rate: Optional[float]  # None means use global rate


def extract_image_sources(html: str) -> List[str]:
    soup = BeautifulSoup(html or "", "html.parser")
    urls: List[str] = []
    for img in soup.find_all("img"):
        src = img.get("src")
        if not src:
            continue
        if src.startswith("http://") or src.startswith("https://"):
            urls.append(src)
    return urls


essential_link_schemes = ("http://", "https://")


def extract_links(html: str) -> List[str]:
    soup = BeautifulSoup(html or "", "html.parser")
    hrefs: List[str] = []
    for a in soup.find_all("a"):
        href = a.get("href")
        if not href:
            continue
        if href.startswith(essential_link_schemes):
            hrefs.append(href)
    # Deduplicate preserving order
    seen = set()
    uniq: List[str] = []
    for u in hrefs:
        if u in seen:
            continue
        seen.add(u)
        uniq.append(u)
    return uniq


def find_exacttarget_open_pixel(html: str) -> Optional[str]:
    """Return the ExactTarget/SFMC open pixel URL if present.

    Specifically searches for an <img> whose src contains
    '://cl.s4.exct.net/open.aspx' (case-insensitive).
    """
    import logging
    logger = logging.getLogger(__name__)
    
    soup = BeautifulSoup(html or "", "html.parser")
    all_imgs = soup.find_all("img")
    
    logger.info("open_pixel_search_start", extra={
        "total_img_tags": len(all_imgs),
        "html_length": len(html) if html else 0,
    })
    
    for idx, img in enumerate(all_imgs):
        src = img.get("src")
        if not src:
            logger.debug("open_pixel_img_no_src", extra={
                "img_index": idx,
            })
            continue
        
        low = src.lower()
        matches_pattern = "://cl.s4.exct.net/open.aspx" in low
        
        logger.info("open_pixel_checking_img", extra={
            "img_index": idx,
            "src": src,
            "src_length": len(src),
            "src_lowercase": low,
            "matches_pattern": matches_pattern,
            "pattern": "://cl.s4.exct.net/open.aspx",
        })
        
        if matches_pattern:
            logger.info("open_pixel_found", extra={
                "img_index": idx,
                "url": src,
            })
            return src
    
    logger.info("open_pixel_not_found", extra={
        "total_imgs_checked": len(all_imgs),
        "all_img_srcs": [img.get("src", "")[:100] for img in all_imgs if img.get("src")],
    })
    return None


def find_global_click_rate(html: str) -> Optional[float]:
    """Find global click rate override from HTML.
    
    Searches for <div data-scope="global" data-click-rate="..."> and returns
    the parsed float value (0.0-1.0). Returns None if not found.
    
    Args:
        html: HTML content to parse
        
    Returns:
        Float value between 0.0 and 1.0, or None if not found
    """
    soup = BeautifulSoup(html or "", "html.parser")
    global_divs = soup.find_all("div", attrs={"data-scope": "global"})
    
    logger.info("global_click_rate_search_start", extra={
        "total_divs_with_scope_global": len(global_divs),
        "html_length": len(html) if html else 0,
    })
    
    for idx, div in enumerate(global_divs):
        click_rate_attr = div.get("data-click-rate")
        if click_rate_attr is None:
            logger.debug("global_click_rate_div_no_attribute", extra={
                "div_index": idx,
            })
            continue
        
        try:
            rate = float(click_rate_attr)
            # Clamp to valid range [0.0, 1.0]
            if rate < 0.0:
                logger.warning("global_click_rate_below_zero", extra={
                    "div_index": idx,
                    "value": rate,
                    "clamped_to": 0.0,
                })
                rate = 0.0
            elif rate > 1.0:
                logger.warning("global_click_rate_above_one", extra={
                    "div_index": idx,
                    "value": rate,
                    "clamped_to": 1.0,
                })
                rate = 1.0
            
            if idx > 0:
                logger.warning("global_click_rate_multiple_divs", extra={
                    "using_first": True,
                    "total_found": len(global_divs),
                })
            
            logger.info("global_click_rate_found", extra={
                "div_index": idx,
                "value": rate,
                "raw_attribute": click_rate_attr,
            })
            return rate
            
        except (ValueError, TypeError) as e:
            logger.warning("global_click_rate_invalid_value", extra={
                "div_index": idx,
                "raw_attribute": click_rate_attr,
                "error": str(e),
            })
            continue
    
    logger.info("global_click_rate_not_found", extra={
        "total_divs_checked": len(global_divs),
    })
    return None


def extract_links_with_rates(html: str, global_rate: Optional[float]) -> List[LinkWithRate]:
    """Extract links from HTML with their individual click rates.
    
    Finds all <a> tags with http:// or https:// URLs and extracts
    their data-click-rate attributes if present.
    
    Args:
        html: HTML content to parse
        global_rate: Global click rate (for logging purposes, not used here)
        
    Returns:
        List of LinkWithRate objects, deduplicated by URL
    """
    soup = BeautifulSoup(html or "", "html.parser")
    links_with_rates: List[LinkWithRate] = []
    seen_urls = set()
    
    for a in soup.find_all("a"):
        href = a.get("href")
        if not href:
            continue
        if not href.startswith(essential_link_schemes):
            continue
        
        # Deduplicate URLs (preserve first occurrence)
        if href in seen_urls:
            continue
        seen_urls.add(href)
        
        # Extract data-click-rate if present
        click_rate_attr = a.get("data-click-rate")
        click_rate = None
        
        if click_rate_attr is not None:
            try:
                rate = float(click_rate_attr)
                # Clamp to valid range [0.0, 1.0]
                if rate < 0.0:
                    logger.warning("link_click_rate_below_zero", extra={
                        "url": href[:100],
                        "value": rate,
                        "clamped_to": 0.0,
                    })
                    rate = 0.0
                elif rate > 1.0:
                    logger.warning("link_click_rate_above_one", extra={
                        "url": href[:100],
                        "value": rate,
                        "clamped_to": 1.0,
                    })
                    rate = 1.0
                click_rate = rate
            except (ValueError, TypeError) as e:
                logger.warning("link_click_rate_invalid_value", extra={
                    "url": href[:100],
                    "raw_attribute": click_rate_attr,
                    "error": str(e),
                })
        
        links_with_rates.append(LinkWithRate(url=href, click_rate=click_rate))
    
    logger.info("extract_links_with_rates_complete", extra={
        "total_links_found": len(links_with_rates),
        "links_with_individual_rates": sum(1 for l in links_with_rates if l.click_rate is not None),
        "links_using_global_rate": sum(1 for l in links_with_rates if l.click_rate is None),
        "global_rate": global_rate,
    })
    
    return links_with_rates
