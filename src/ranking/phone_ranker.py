from __future__ import annotations
import re

def choose_best_phone(phones: list[str]) -> str | None:
    if not phones:
        return None

    unique = sorted({p.strip() for p in phones if p and p.strip()})
    if not unique:
        return None

    def score(p: str) -> tuple:
        digits = re.sub(r"\D", "", p)
        return (
            0 if p.strip().startswith("+") else 1,     # prefer +country format
            -len(digits),                              # prefer more digits
            p                                          # stable tie-break
        )

    return sorted(unique, key=score)[0]
