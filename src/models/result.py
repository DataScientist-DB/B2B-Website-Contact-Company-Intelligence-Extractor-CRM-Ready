from __future__ import annotations

from typing import Any, Dict, List, Optional


_ROLE_HINTS = {
    "sales": ("sales@", "bizdev@", "business@", "partners@", "partnership@", "bd@"),
    "support": ("support@", "help@", "service@", "success@", "cs@", "care@"),
    "press": ("press@", "media@", "pr@"),
    "careers": ("jobs@", "careers@", "hr@", "talent@"),
    "legal": ("legal@", "privacy@", "dpo@"),
    "general": ("info@", "hello@", "contact@", "office@", "admin@"),
}


def _classify_email_role(email: Optional[str]) -> str:
    if not email:
        return ""
    e = email.strip().lower()
    for role, prefixes in _ROLE_HINTS.items():
        if any(p in e for p in prefixes):
            return role
    return "other" if "@" in e else ""


def _confidence_email(best_email: Optional[str], emails: List[str]) -> float:
    if not best_email:
        return 0.0
    role = _classify_email_role(best_email)
    base = 0.85 if role in ("sales", "support", "press", "general") else 0.70
    if len(emails) >= 3:
        base += 0.05
    return min(1.0, base)


def _confidence_phone(best_phone: Optional[str], phones: List[str]) -> float:
    if not best_phone:
        return 0.0
    base = 0.75
    if len(phones) >= 2:
        base += 0.05
    return min(1.0, base)


def build_result(
    input_url: str,
    final_url: str,
    company_name: Optional[str] = None,
    best_email: Optional[str] = None,
    best_phone: Optional[str] = None,
    emails: Optional[List[str]] = None,
    phones: Optional[List[str]] = None,
    socials: Optional[Dict[str, Any]] = None,
    evidence: Optional[List[Dict[str, Any]]] = None,
    contact_page: Optional[str] = None,
    address_text: Optional[str] = None,
    status_override: Optional[str] = None,
    error: Optional[str] = None,
    pages_scanned_count: Optional[int] = None,
    # ---- NEW (10× value) fields ----
    industry: Optional[str] = None,
    country: Optional[str] = None,
    linkedin_company_url: Optional[str] = None,
    contact_form_url: Optional[str] = None,
    google_maps_url: Optional[str] = None,
    company_size_estimate: Optional[str] = None,
    # ---- BACKWARD-COMPAT ALIASES / FUTURE-PROOF ----
    organization_name: Optional[str] = None,  # alias -> company_name
    **kwargs: Any,  # ignore unknown future fields safely
) -> Dict[str, Any]:
    """
    Build one result row.

    Compatibility:
    - Accepts organization_name (older/newer callers) and maps it to company_name.
    - Accepts **kwargs to avoid crashing when core adds new fields.
    """
    # alias mapping
    if company_name is None and organization_name:
        company_name = organization_name

    emails = emails or []
    phones = phones or []
    socials = socials or {}
    evidence = evidence or []

    # keep evidence lightweight
    if len(evidence) > 30:
        evidence = evidence[:30]

    role = _classify_email_role(best_email)

    status = status_override or ("OK" if (emails or phones or socials or address_text) else "EMPTY")

    # ---- company_name FIRST column ----
    return {
        "organization_name": company_name,

        # value add
        "industry": industry,
        "country": country,
        "linkedin_company_url": linkedin_company_url,
        "company_size_estimate": company_size_estimate,
        "contact_form_url": contact_form_url,
        "google_maps_url": google_maps_url,

        # core fields
        "input_url": input_url,
        "final_url": final_url,
        "best_email": best_email,
        "best_phone": best_phone,
        "emails": emails,
        "phones": phones,
        "address_text": address_text,
        "socials": socials,
        "contact_page": contact_page,
        "evidence": evidence,

        "status": status,
        "error": error,

        "emails_count": len(emails),
        "phones_count": len(phones),
        "socials_count": len([k for k, v in socials.items() if v]),
        "best_email_role": role,
        "confidence_email": _confidence_email(best_email, emails),
        "confidence_phone": _confidence_phone(best_phone, phones),
        "pages_scanned_count": pages_scanned_count,

        # useful for debugging if you want to surface ignored fields later:
        # "_ignored_fields": list(kwargs.keys()) if kwargs else [],
    }