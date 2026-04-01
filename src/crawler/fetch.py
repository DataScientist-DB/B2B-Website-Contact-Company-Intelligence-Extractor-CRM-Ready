from __future__ import annotations

from typing import Dict

import requests


# --------------------------------
# HTTP configuration (profit-safe)
# --------------------------------

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; WebsiteContactExtractor/1.0)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Connection": "keep-alive",
}

# Reuse connections (big speed boost)
SESSION = requests.Session()
SESSION.headers.update(HEADERS)

# Hard limits (important for Actor profitability)
REQUEST_TIMEOUT = 12       # seconds
MAX_HTML_SIZE = 2_000_000  # 2 MB
MAX_REDIRECTS = 10


def _is_likely_html(resp: requests.Response) -> bool:
    ct = (resp.headers.get("Content-Type") or "").lower()
    # allow empty content-type (some servers) but reject obvious non-html
    if not ct:
        return True
    return ("text/html" in ct) or ("application/xhtml+xml" in ct) or ("text/plain" in ct)


def fetch_page(url: str) -> Dict[str, object]:
    """
    Lightweight HTML fetcher used by the crawler.

    Designed to keep Apify Actor runs fast and cheap:
    - connection reuse (Session)
    - strict timeout
    - caps downloaded bytes (MAX_HTML_SIZE)
    - avoids non-HTML content
    - safe error handling
    """
    try:
        resp = SESSION.get(
            url,
            timeout=REQUEST_TIMEOUT,
            allow_redirects=True,
            stream=True,
        )

        # follow_redirects=True can still end in many redirects; protect the run
        if len(getattr(resp, "history", []) or []) > MAX_REDIRECTS:
            return {
                "url": url,
                "final_url": url,
                "html": "",
                "status_code": 310,  # too many redirects (custom-ish)
                "error": f"Too many redirects ({len(resp.history)})",
            }

        status = resp.status_code

        # quick non-HTML guard (saves time on PDFs/images)
        if not _is_likely_html(resp):
            return {
                "url": url,
                "final_url": resp.url,
                "html": "",
                "status_code": status,
                "error": f"Non-HTML Content-Type: {resp.headers.get('Content-Type')}",
            }

        resp.raise_for_status()

        # Limit HTML size to avoid huge pages slowing the run
        content = resp.raw.read(MAX_HTML_SIZE, decode_content=True)  # type: ignore[attr-defined]
        encoding = resp.encoding or "utf-8"
        html = content.decode(encoding, errors="replace")

        return {
            "url": url,
            "final_url": resp.url,
            "html": html,
            "status_code": status,
        }

    except requests.exceptions.Timeout:
        return {
            "url": url,
            "final_url": url,
            "html": "",
            "status_code": 408,
            "error": "Timeout",
        }

    except requests.exceptions.TooManyRedirects:
        return {
            "url": url,
            "final_url": url,
            "html": "",
            "status_code": 310,
            "error": "TooManyRedirects",
        }

    except requests.exceptions.RequestException as e:
        # Includes DNS failures, SSL issues, connection errors, 4xx/5xx after raise_for_status, etc.
        return {
            "url": url,
            "final_url": url,
            "html": "",
            "status_code": 500,
            "error": str(e),
        }