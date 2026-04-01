from __future__ import annotations

import asyncio
import json
import re
from typing import Any, Dict, Optional
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from src.crawler.fetch import fetch_page
from src.crawler.page_discovery import discover_pages
from src.extractors.emails import extract_emails
from src.extractors.phones import extract_phones
from src.extractors.socials import extract_socials
from src.models.result import build_result
from src.ranking.email_ranker import choose_best_email
from src.ranking.phone_ranker import choose_best_phone
from src.utils.url import normalize_url


# -----------------------------------------------------------------------------
# Company name / brand
# -----------------------------------------------------------------------------
def _brand_from_url(url: str | None) -> str | None:
    if not url:
        return None
    host = (urlparse(url).netloc or "").lower()
    if host.startswith("www."):
        host = host[4:]
    if not host:
        return None

    parts = host.split(".")
    brand = parts[-2] if len(parts) >= 2 else parts[0]
    brand = re.sub(r"[^a-z0-9\-]", "", brand)
    if not brand:
        return None
    return brand.replace("-", " ").strip().title()


def _extract_company_name(html: str, fallback_url: str | None = None) -> str | None:
    if not html:
        return _brand_from_url(fallback_url)

    soup = BeautifulSoup(html, "lxml")

    def clean(s: str) -> str:
        s = " ".join((s or "").split()).strip()
        s = re.sub(
            r"\b(contact|contact us|about|about us|home|welcome|locations|careers|jobs|support)\b",
            "",
            s,
            flags=re.I,
        )
        s = re.sub(r"\s{2,}", " ", s).strip(" -|•—:")
        return s.strip()

    def is_good_brand(s: str) -> bool:
        if not s:
            return False
        s = s.strip()
        if len(s) > 40:
            return False
        if len(s.split()) > 6:
            return False
        bad = ("services", "solutions", "official website", "learn more", "best", "leading")
        if any(b in s.lower() for b in bad):
            return False
        return True

    # 1) og:site_name
    og = soup.find("meta", property="og:site_name")
    if og and og.get("content"):
        cand = clean(og["content"])
        if is_good_brand(cand):
            return cand

    # 2) JSON-LD Organization name
    for s in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = (s.string or "").strip()
        if not raw:
            continue
        try:
            data = json.loads(raw)
            nodes = data if isinstance(data, list) else [data]
            for obj in nodes:
                if not isinstance(obj, dict):
                    continue
                graph = obj.get("@graph")
                candidates = graph if isinstance(graph, list) else [obj]
                for node in candidates:
                    if not isinstance(node, dict):
                        continue
                    t = node.get("@type")
                    if t in ("Organization", "LocalBusiness"):
                        nm = node.get("name")
                        if isinstance(nm, str):
                            cand = clean(nm)
                            if is_good_brand(cand):
                                return cand
        except Exception:
            continue

    # 3) <title>
    if soup.title and soup.title.string:
        t = soup.title.string.strip()
        for sep in ("|", "—", "•", "·"):
            if sep in t:
                t = t.split(sep, 1)[0].strip()
        cand = clean(t)
        if is_good_brand(cand):
            return cand

    # 4) fallback: domain brand
    return _brand_from_url(fallback_url)


# -----------------------------------------------------------------------------
# Address (cheap heuristics)
# -----------------------------------------------------------------------------
def _extract_address_text(html: str) -> str | None:
    if not html:
        return None

    soup = BeautifulSoup(html, "lxml")

    def clean(txt: str) -> str | None:
        t = " ".join((txt or "").split())
        return t if len(t) >= 10 else None

    # 1) <address>
    addr = soup.find("address")
    if addr:
        t = clean(addr.get_text(" ", strip=True))
        if t:
            return t

    # 2) Microformats / vCard
    vcard = soup.select_one(".vcard, .h-card, .adr, .p-adr")
    if vcard:
        t = clean(vcard.get_text(" ", strip=True))
        if t:
            return t

    # 3) class/id contains address
    block = soup.find(
        lambda tag: tag.name in ("div", "p", "section", "footer")
        and (
            ("address" in " ".join(tag.get("class", [])).lower())
            or ("address" in (tag.get("id") or "").lower())
        )
    )
    if block:
        t = clean(block.get_text(" ", strip=True))
        if t:
            return t

    # 4) microdata itemprop
    parts: list[str] = []
    for prop in ("streetAddress", "addressLocality", "addressRegion", "postalCode", "addressCountry"):
        el = soup.find(attrs={"itemprop": prop})
        if el:
            val = clean(el.get_text(" ", strip=True))
            if val:
                parts.append(val)
    if parts:
        return ", ".join(parts)

    # 5) JSON-LD PostalAddress
    for s in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = (s.string or "").strip()
        if not raw:
            continue
        try:
            data = json.loads(raw)
            nodes = data if isinstance(data, list) else [data]
            for obj in nodes:
                if not isinstance(obj, dict):
                    continue
                graph = obj.get("@graph")
                nodes2 = graph if isinstance(graph, list) else [obj]
                for node in nodes2:
                    if not isinstance(node, dict):
                        continue
                    addr_obj = node.get("address")
                    if isinstance(addr_obj, dict):
                        parts2: list[str] = []
                        for k in ("streetAddress", "addressLocality", "addressRegion", "postalCode", "addressCountry"):
                            v = addr_obj.get(k)
                            if isinstance(v, str) and v.strip():
                                parts2.append(v.strip())
                        if parts2:
                            return ", ".join(parts2)
        except Exception:
            continue

    # 6) Footer heuristic
    footer = soup.find("footer")
    if footer:
        txt = footer.get_text(" ", strip=True)
        m = re.search(
            r"\d{1,5}\s+[A-Za-z0-9\s\.\-]+(?:Street|St|Road|Rd|Ave|Avenue|Blvd|Drive|Dr|Lane|Ln)",
            txt,
            re.I,
        )
        if m:
            return m.group(0)

    return None


# -----------------------------------------------------------------------------
# Value-add fields (lightweight)
# -----------------------------------------------------------------------------
def _detect_country(url: str) -> str | None:
    if not url:
        return None
    host = (urlparse(url).netloc or "").lower()
    tld_map = {
        ".ca": "Canada",
        ".us": "United States",
        ".uk": "United Kingdom",
        ".au": "Australia",
        ".de": "Germany",
        ".fr": "France",
        ".nl": "Netherlands",
        ".se": "Sweden",
        ".no": "Norway",
        ".dk": "Denmark",
        ".fi": "Finland",
        ".ch": "Switzerland",
    }
    for tld, country in tld_map.items():
        if host.endswith(tld):
            return country
    return None


def _detect_industry_light(html: str) -> str | None:
    if not html:
        return None
    t = html.lower()
    rules = {
        "Recruitment / HR": ("recruit", "staffing", "talent", "hiring", "hr"),
        "Government": ("municipal", "city of", "government", "public services"),
        "Nonprofit": ("nonprofit", "donate", "charity", "foundation"),
        "Education": ("university", "college", "school", "campus"),
        "Healthcare": ("clinic", "medical", "hospital", "healthcare"),
        "Technology": ("software", "platform", "technology", "cloud"),
        "Retail": ("shop", "store", "ecommerce", "buy now"),
    }
    for industry, kws in rules.items():
        if any(k in t for k in kws):
            return industry
    return None


def _extract_linkedin_company_url(html: str, socials: dict) -> str | None:
    if isinstance(socials, dict):
        for _, v in socials.items():
            if isinstance(v, str) and "linkedin.com" in v.lower() and "/company/" in v.lower():
                return v
    if not html:
        return None
    for href in re.findall(r'href=["\']([^"\']+)["\']', html, re.I):
        hl = href.lower()
        if "linkedin.com" in hl and "/company/" in hl:
            return href
    return None


def _extract_google_maps_url(html: str) -> str | None:
    if not html:
        return None
    for href in re.findall(r'href=["\']([^"\']+)["\']', html, re.I):
        hl = href.lower()
        if "google.com/maps" in hl or "goo.gl/maps" in hl or "maps.app.goo.gl" in hl:
            return href
    return None


def _estimate_company_size(html: str) -> str | None:
    if not html:
        return None
    t = re.sub(r"\s+", " ", html.lower())
    m = re.search(r"(\d{1,4}(?:,\d{3})?)(\+)?\s+employees", t)
    if m:
        return m.group(1) + ("+" if m.group(2) else "")
    m2 = re.search(r"numberofemployees[^0-9]{0,40}(\d{1,6})", t)
    if m2:
        return m2.group(1)
    return None


def _detect_contact_form_url(html: str, page_url: str) -> str | None:
    if not html:
        return None
    return page_url if re.search(r"<form\b", html, re.I) else None


# -----------------------------------------------------------------------------
# Concurrent bridge: one site -> one row
# (Bridge uses run_core in a thread; later you can refactor to true async HTTP.)
# -----------------------------------------------------------------------------
async def run_one_site(url: str, config: Dict[str, Any], client: Any = None) -> Optional[Dict[str, Any]]:
    try:
        single_input = dict(config)
        single_input["startUrls"] = [{"url": url}]
        single_input["maxSites"] = 1

        # run_core is sync; run it in a thread so main.py can do concurrency safely
        results = await asyncio.to_thread(run_core, single_input)

        if results and isinstance(results, list) and results[0] and isinstance(results[0], dict):
            return results[0]

        return build_result(
            input_url=url,
            final_url=url,
            company_name=None,
            best_email=None,
            best_phone=None,
            emails=[],
            phones=[],
            socials={},
            evidence=[],
            contact_page=None,
            address_text=None,
            status_override="EMPTY",
            error="No results returned by run_one_site()",
        )
    except Exception as e:
        return build_result(
            input_url=url,
            final_url=url,
            company_name=None,
            best_email=None,
            best_phone=None,
            emails=[],
            phones=[],
            socials={},
            evidence=[],
            contact_page=None,
            address_text=None,
            status_override="FAILED",
            error=str(e),
        )


# -----------------------------------------------------------------------------
# Core (sync) — your existing extraction logic
# -----------------------------------------------------------------------------
def run_core(input_data: dict) -> list[dict]:
    start_urls = input_data.get("startUrls", []) or []

    try:
        max_extra_pages = int(input_data.get("maxPagesPerSite", 1))
    except Exception:
        max_extra_pages = 1

    max_extra_pages = max(0, min(10, max_extra_pages))
    extract_social = bool(input_data.get("extractSocialLinks", False))

    results: list[dict] = []

    for req in start_urls:
        url = normalize_url((req or {}).get("url"))
        if not url:
            continue

        # Defaults so exception handler can safely build a FAILED row
        final_home_url = url
        all_emails: set[str] = set()
        all_phones: set[str] = set()
        evidence: list[dict] = []
        contact_page: str | None = None
        pages_scanned = 0

        company_name: str | None = None
        address_text: str | None = None
        socials: dict = {}

        industry: str | None = None
        country: str | None = None
        linkedin_company_url: str | None = None
        contact_form_url: str | None = None
        google_maps_url: str | None = None
        company_size_estimate: str | None = None

        best_email: str | None = None
        best_phone: str | None = None

        try:
            # 1) Fetch homepage once
            homepage = fetch_page(url)
            final_home_url = homepage.get("final_url") or url
            homepage_html = homepage.get("html") or ""

            # 2) Discover candidate pages
            extra_pages = discover_pages(homepage, max_extra_pages) or []

            # 3) Scan homepage
            emails, email_ev = extract_emails(homepage_html, final_home_url)
            phones, phone_ev = extract_phones(homepage_html, final_home_url)
            all_emails.update(emails or [])
            all_phones.update(phones or [])
            evidence.extend((email_ev or []) + (phone_ev or []))
            pages_scanned += 1

            company_name = _extract_company_name(homepage_html, final_home_url)
            address_text = _extract_address_text(homepage_html)

            socials = extract_socials(homepage) if extract_social else {}

            # value-add (homepage)
            industry = _detect_industry_light(homepage_html)
            country = _detect_country(final_home_url)
            linkedin_company_url = _extract_linkedin_company_url(homepage_html, socials)
            google_maps_url = _extract_google_maps_url(homepage_html)
            company_size_estimate = _estimate_company_size(homepage_html)
            contact_form_url = _detect_contact_form_url(homepage_html, final_home_url)

            # 4) Scan discovered pages
            for page_url in extra_pages:
                if not page_url:
                    continue

                pl = page_url.lower()
                if contact_page is None and any(
                    k in pl
                    for k in (
                        "contact",
                        "about",
                        "impressum",
                        "support",
                        "help",
                        "location",
                        "locations",
                        "office",
                        "offices",
                        "directions",
                        "find-us",
                        "findus",
                        "visit",
                    )
                ):
                    contact_page = page_url

                page = fetch_page(page_url)
                html = page.get("html") or ""
                if not html:
                    continue

                pages_scanned += 1

                # cheap first
                if not address_text:
                    address_text = _extract_address_text(html)
                if not company_name:
                    company_name = _extract_company_name(html, page_url)

                # value-add from extra pages
                if not google_maps_url:
                    google_maps_url = _extract_google_maps_url(html)
                if not linkedin_company_url:
                    linkedin_company_url = _extract_linkedin_company_url(html, socials)
                if not company_size_estimate:
                    company_size_estimate = _estimate_company_size(html)
                if not contact_form_url:
                    cf = _detect_contact_form_url(html, page_url)
                    if cf:
                        contact_form_url = cf

                # extract contacts
                ems, em_ev = extract_emails(html, page_url)
                phs, ph_ev = extract_phones(html, page_url)
                all_emails.update(ems or [])
                all_phones.update(phs or [])
                if em_ev or ph_ev:
                    evidence.extend((em_ev or []) + (ph_ev or []))

                # early stop
                if address_text and (all_emails or all_phones):
                    break

            # 5) Choose best contacts
            best_email = choose_best_email(sorted(all_emails))
            best_phone = choose_best_phone(sorted(all_phones))

            results.append(
                build_result(
                    input_url=url,
                    final_url=final_home_url,
                    company_name=company_name,
                    best_email=best_email,
                    best_phone=best_phone,
                    emails=sorted(all_emails),
                    phones=sorted(all_phones),
                    socials=socials,
                    evidence=evidence,
                    contact_page=contact_page,
                    address_text=address_text,
                    pages_scanned_count=pages_scanned,
                    industry=industry,
                    country=country,
                    linkedin_company_url=linkedin_company_url,
                    contact_form_url=contact_form_url,
                    google_maps_url=google_maps_url,
                    company_size_estimate=company_size_estimate,
                )
            )

        except Exception as e:
            results.append(
                build_result(
                    input_url=url,
                    final_url=final_home_url,
                    company_name=company_name,
                    best_email=best_email,
                    best_phone=best_phone,
                    emails=sorted(all_emails),
                    phones=sorted(all_phones),
                    socials=socials,
                    evidence=evidence,
                    contact_page=contact_page,
                    address_text=address_text,
                    pages_scanned_count=pages_scanned,
                    industry=industry,
                    country=country,
                    linkedin_company_url=linkedin_company_url,
                    contact_form_url=contact_form_url,
                    google_maps_url=google_maps_url,
                    company_size_estimate=company_size_estimate,
                    status_override="FAILED",
                    error=str(e),
                )
            )

    return results