from urllib.parse import urlparse

def normalize_url(url: str | None) -> str | None:
    """
    Normalize and validate a URL.
    - Adds https:// if scheme missing
    - Rejects clearly invalid inputs
    """
    if not url:
        return None
    url = url.strip()
    if not url:
        return None

    # add scheme if missing
    if "://" not in url:
        url = "https://" + url

    try:
        p = urlparse(url)
        if not p.netloc:
            return None
        return url
    except Exception:
        return None
