from __future__ import annotations
import re
from bs4 import BeautifulSoup

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")

DEPRIORITIZE_PREFIXES = (
    "noreply@", "no-reply@", "donotreply@", "do-not-reply@", "webmaster@"
)

def extract_emails(html: str, source_url: str):
    html = html or ""
    soup = BeautifulSoup(html, "lxml")

    found = set()

    # mailto:
    for a in soup.select('a[href^="mailto:"]'):
        href = a.get("href") or ""
        v = href.split("mailto:", 1)[-1].split("?", 1)[0].strip()
        if v:
            found.add(v.lower())

    # visible text emails
    for e in EMAIL_RE.findall(html):
        found.add(e.lower())

    # basic de-obfuscation: "name [at] domain [dot] com"
    cleaned_text = re.sub(r"\s+", " ", soup.get_text(" ", strip=True).lower())
    cleaned_text = cleaned_text.replace("[at]", "@").replace("(at)", "@").replace(" at ", "@")
    cleaned_text = cleaned_text.replace("[dot]", ".").replace("(dot)", ".").replace(" dot ", ".")
    for e in EMAIL_RE.findall(cleaned_text):
        found.add(e.lower())

    found = {e for e in found if not e.startswith(DEPRIORITIZE_PREFIXES)}

    evidence = [{"type": "email", "value": e, "sourceUrl": source_url} for e in sorted(found)]
    return sorted(found), evidence
