from __future__ import annotations
from typing import List, Optional
from bs4 import BeautifulSoup


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
