from __future__ import annotations

from io import BytesIO
from typing import Optional

import pandas as pd


def df_to_csv_bytes(df: pd.DataFrame) -> bytes:
    buf = BytesIO()
    df.to_csv(buf, index=False)
    return buf.getvalue()


def df_to_xlsx_bytes(df: pd.DataFrame, sheet_name: str = "data") -> bytes:
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name=sheet_name[:31])
    return buf.getvalue()


def safe_dataframe(items: list[dict]) -> pd.DataFrame:
    """
    Robust conversion:
    - handles empty
    - flattens top-level keys
    """
    if not items:
        return pd.DataFrame()
    return pd.json_normalize(items)


def pick_columns(df: pd.DataFrame, preferred: Optional[list[str]] = None) -> pd.DataFrame:
    """
    Optional: order columns (keeps any extras at the end).
    """
    if df.empty:
        return df
    if not preferred:
        return df

    existing = [c for c in preferred if c in df.columns]
    remaining = [c for c in df.columns if c not in existing]
    return df[existing + remaining]