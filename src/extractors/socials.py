from bs4 import BeautifulSoup

SOCIAL_DOMAINS = {
    "linkedin.com": "linkedin",
    "facebook.com": "facebook",
    "twitter.com": "twitter",
    "x.com": "twitter",
    "instagram.com": "instagram",
    "youtube.com": "youtube",
}

def extract_socials(page: dict) -> dict:
    """
    Passive extraction only:
    reads social URLs present on the org website HTML.
    Does NOT crawl social sites.
    """
    html = page.get("html") or ""
    soup = BeautifulSoup(html, "lxml")

    out = {k: None for k in ["linkedin", "facebook", "twitter", "instagram", "youtube"]}

    for a in soup.select("a[href]"):
        href = (a.get("href") or "").strip()
        if not href:
            continue
        href_l = href.lower()

        for domain, key in SOCIAL_DOMAINS.items():
            if domain in href_l:
                if out.get(key) is None:
                    out[key] = href
                break

    return {k: v for k, v in out.items() if v}
