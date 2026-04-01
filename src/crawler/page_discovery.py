from __future__ import annotations

from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, urldefrag

POSITIVE = (
    "contact", "contact-us", "contactus",
    "support", "help", "customer-service",
    "about", "impressum",
    "location", "locations", "find-us", "findus", "visit", "office", "offices", "directions"
)
NEGATIVE = (
    "donat", "giving", "foundation", "fund", "sponsor", "corporate",
    "shop", "store", "cart", "checkout", "privacy", "terms", "jobs", "careers"
)

BAD_SCHEMES_PREFIXES = ("mailto:", "tel:", "sms:")
BAD_EXTS = (
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".ico",
    ".zip", ".rar", ".7z", ".mp4", ".mov", ".avi", ".mp3", ".wav",
)


def _same_domain(base: str, target: str) -> bool:
    try:
        b = urlparse(base)
        t = urlparse(target)
        return (b.netloc and t.netloc and b.netloc.lower() == t.netloc.lower())
    except Exception:
        return False


def _is_good_candidate_url(u: str) -> bool:
    if not u:
        return False
    ul = u.strip().lower()
    if ul.startswith(BAD_SCHEMES_PREFIXES):
        return False
    if not ul.startswith("http"):
        return False
    if ul.endswith(BAD_EXTS):
        return False

    parsed = urlparse(u)
    if parsed.query and len(parsed.query) > 180:
        return False

    return True


def _score(u: str) -> int:
    """Higher score = more likely to contain contact + address."""
    ul = u.lower()
    s = 0

    # strongest
    if "/contact" in ul or "contact-us" in ul or "contactus" in ul:
        s += 120

    # support/help
    if "support" in ul or "help" in ul or "customer-service" in ul:
        s += 80

    # address-heavy pages (your missing piece)
    if "location" in ul or "locations" in ul:
        s += 90
    if "find-us" in ul or "findus" in ul or "directions" in ul:
        s += 85
    if "visit" in ul:
        s += 70
    if "office" in ul or "offices" in ul:
        s += 65

    # medium
    if "about" in ul or "impressum" in ul:
        s += 35

    # weak but sometimes contains address blocks
    if "legal" in ul or "terms" in ul or "privacy" in ul:
        s += 5

    return s

def discover_pages(homepage: dict, max_pages: int) -> list[str]:
    """
    Return ONLY extra pages (not including homepage).
    Prevents duplicate homepage fetch and keeps runs cheap.
    """
    base_url = homepage.get("final_url") or homepage.get("url") or ""
    if not base_url:
        return []

    if max_pages <= 0:
        return []

    html = homepage.get("html") or ""
    if not html.strip():
        return []

    soup = BeautifulSoup(html, "lxml")
    candidates: list[str] = []

    for a in soup.select("a[href]"):
        href = (a.get("href") or "").strip()
        if not href:
            continue

        abs_url = urljoin(base_url, href)
        abs_url, _frag = urldefrag(abs_url)

        if not _is_good_candidate_url(abs_url):
            continue
        if not _same_domain(base_url, abs_url):
            continue

        if abs_url.rstrip("/") == base_url.rstrip("/"):
            continue

        text = " ".join(a.get_text(" ", strip=True).split()).lower()
        href_l = abs_url.lower()

        if any(n in href_l for n in NEGATIVE) or any(n in text for n in NEGATIVE):
            continue

        if any(p in href_l for p in POSITIVE) or any(p in text for p in POSITIVE):
            candidates.append(abs_url)

    seen = set()
    deduped: list[str] = []
    for u in candidates:
        if u not in seen:
            seen.add(u)
            deduped.append(u)

    deduped.sort(key=_score, reverse=True)

    return deduped[:max_pages]