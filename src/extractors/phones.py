from __future__ import annotations

import json
import re
from bs4 import BeautifulSoup
import phonenumbers

PHONE_LIKE_RE = re.compile(r"(\+?\d[\d\s().-]{7,}\d)")

def _from_jsonld(html: str) -> set[str]:
    soup = BeautifulSoup(html or "", "lxml")
    out = set()
    for s in soup.select('script[type="application/ld+json"]'):
        txt = (s.string or "").strip()
        if not txt:
            continue
        try:
            data = json.loads(txt)
        except Exception:
            continue

        def walk(x):
            if isinstance(x, dict):
                for k, v in x.items():
                    if k in ("telephone", "phone", "contactPoint", "contactPoints"):
                        walk(v)
                    else:
                        walk(v)
            elif isinstance(x, list):
                for item in x:
                    walk(item)
            elif isinstance(x, str):
                for m in PHONE_LIKE_RE.findall(x):
                    out.add(m)

        walk(data)
    return out

def _format_phone(raw: str) -> str | None:
    raw = (raw or "").strip()
    if not raw:
        return None

    # quick cleanup for odd strings like "877) 272-7337"
    raw = re.sub(r"\s+", " ", raw)
    raw = raw.replace(") ", ")")
    raw = raw.replace(" )", ")")
    raw = raw.strip()

    # Filter ZIP/ZIP+4 patterns like 31709-3543
    if re.fullmatch(r"\d{5}(-\d{4})?", raw):
        return None

    # Extract digits for parsing; keep + if present
    digits = re.sub(r"[^\d+]", "", raw)

    # Try parse as US by default if 10 digits (common for org sites)
    try:
        if digits.startswith("+"):
            num = phonenumbers.parse(digits, None)
        else:
            # If looks like US 10-digit or toll-free without country
            if len(re.sub(r"\D", "", digits)) in (10, 11):
                num = phonenumbers.parse(digits, "US")
            else:
                num = phonenumbers.parse(digits, None)

        if phonenumbers.is_possible_number(num) and phonenumbers.is_valid_number(num):
            return phonenumbers.format_number(num, phonenumbers.PhoneNumberFormat.INTERNATIONAL)
    except Exception:
        pass

    # fallback: return original if it still looks phone-like
    if len(re.sub(r"\D", "", raw)) >= 8:
        return raw
    return None

def extract_phones(html: str, source_url: str):
    html = html or ""
    soup = BeautifulSoup(html, "lxml")
    found_raw = set()

    # tel: links
    for a in soup.select('a[href^="tel:"]'):
        href = a.get("href") or ""
        v = href.split("tel:", 1)[-1].split("?", 1)[0].strip()
        if v:
            found_raw.add(v)

    # JSON-LD / schema.org
    found_raw.update(_from_jsonld(html))

    # text parsing
    text = soup.get_text(" ", strip=True)

    for match in phonenumbers.PhoneNumberMatcher(text, "US"):
        found_raw.add(phonenumbers.format_number(match.number, phonenumbers.PhoneNumberFormat.INTERNATIONAL))

    for m in PHONE_LIKE_RE.findall(text):
        found_raw.add(m)

    cleaned = set()
    for p in found_raw:
        fp = _format_phone(str(p))
        if fp:
            cleaned.add(fp)

    evidence = [{"type": "phone", "value": p, "sourceUrl": source_url} for p in sorted(cleaned)]
    return sorted(cleaned), evidence
