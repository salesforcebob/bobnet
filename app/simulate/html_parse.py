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
    soup = BeautifulSoup(html or "", "html.parser")
    for img in soup.find_all("img"):
        src = img.get("src")
        if not src:
            continue
        low = src.lower()
        if "://cl.s4.exct.net/open.aspx" in low:
            return src
    return None
