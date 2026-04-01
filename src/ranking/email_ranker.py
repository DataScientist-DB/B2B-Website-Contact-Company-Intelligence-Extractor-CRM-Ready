from __future__ import annotations

PRIORITY_PREFIXES = (
    "info@",
    "contact@",
    "support@",
    "hello@",
    "sales@",
    "office@",
    "admin@",
)

DEPRIORITIZE_PREFIXES = (
    "noreply@",
    "no-reply@",
    "donotreply@",
    "do-not-reply@",
    "webmaster@",
)

def choose_best_email(emails: list[str]) -> str | None:
    """
    Pick the best org-level email.
    Strategy:
      1) remove obvious non-contact/system emails
      2) prefer common org inboxes (info/contact/support)
      3) otherwise return first deterministic option
    """
    if not emails:
        return None

    cleaned = []
    for e in emails:
        if not e:
            continue
        e2 = e.strip().lower()
        if e2:
            cleaned.append(e2)

    if not cleaned:
        return None

    filtered = [e for e in cleaned if not e.startswith(DEPRIORITIZE_PREFIXES)]
    candidates = filtered if filtered else cleaned

    for pref in PRIORITY_PREFIXES:
        for e in candidates:
            if e.startswith(pref):
                return e

    return sorted(set(candidates))[0]
