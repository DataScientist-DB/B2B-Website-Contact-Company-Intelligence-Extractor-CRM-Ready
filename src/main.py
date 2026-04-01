from __future__ import annotations

import asyncio
import csv
import hashlib
import json
import math
import os
from datetime import datetime
from decimal import Decimal
from io import StringIO, BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional

from apify import Actor
from openpyxl import Workbook

from src.core import run_core
from src.models.result import build_result

print(">>> src/main.py loaded")  # hard proof the module is executed


# -----------------------------
# JSON safety helpers (STRICT)
# -----------------------------
def _json_safe(value: Any) -> Any:
    """Strict JSON-safe conversion (Apify dataset safe)."""
    if value is None:
        return None

    # primitives
    if isinstance(value, (str, int, bool)):
        return value

    if isinstance(value, float):
        # strict JSON disallows NaN/Infinity
        if math.isnan(value) or math.isinf(value):
            return None
        return value

    if isinstance(value, Decimal):
        return float(value)

    if isinstance(value, datetime):
        return value.isoformat()

    # bytes
    if isinstance(value, (bytes, bytearray)):
        return value.decode("utf-8", errors="replace")

    # containers
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}

    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]

    if isinstance(value, set):
        return sorted([_json_safe(v) for v in value], key=lambda x: str(x))

    # fallback for any other object (Path, custom classes, etc.)
    return str(value)


def _force_jsonable(obj: Any) -> Any:
    """Ensure json.dumps can serialize the object."""
    safe = _json_safe(obj)
    try:
        json.dumps(safe)
        return safe
    except TypeError:
        return str(safe)


def _flatten_row(row: Dict[str, Any]) -> Dict[str, Any]:
    """
    Make a row safe for CSV/XLSX:
    - primitives stay
    - lists/dicts/objects become JSON strings (UTF-8 safe)
    """
    out: Dict[str, Any] = {}
    for k, v in (row or {}).items():
        vv = _json_safe(v)
        if vv is None or isinstance(vv, (str, int, float, bool)):
            out[k] = vv
        else:
            out[k] = json.dumps(vv, ensure_ascii=False)
    return out


def _ordered_headers(rows: List[Dict[str, Any]]) -> List[str]:
    rows2 = [_flatten_row(r) for r in (rows or [])]
    keys = {k for r in rows2 for k in r.keys()}

    # Force company_name first
    ordered: List[str] = []
    if "organization_name" in keys:
        ordered.append("organization_name")
        keys.remove("organization_name")

    # Keep the rest stable
    ordered.extend(sorted(keys))
    return ordered


def _make_csv_bytes(rows: List[Dict[str, Any]]) -> bytes:
    rows2 = [_flatten_row(r) for r in (rows or [])]
    headers: List[str] = _ordered_headers(rows)

    buf = StringIO()
    writer = csv.DictWriter(buf, fieldnames=headers, extrasaction="ignore")
    writer.writeheader()
    for r in rows2:
        writer.writerow(r)
    return buf.getvalue().encode("utf-8")


def _make_xlsx_bytes(rows: List[Dict[str, Any]]) -> bytes:
    rows2 = [_flatten_row(r) for r in (rows or [])]
    headers: List[str] = _ordered_headers(rows)

    wb = Workbook()
    ws = wb.active
    ws.title = "data"

    ws.append(headers)
    for r in rows2:
        ws.append([r.get(h, "") for h in headers])

    bio = BytesIO()
    wb.save(bio)
    return bio.getvalue()


def _get_first_url(input_data: Dict[str, Any]) -> Optional[str]:
    try:
        start_urls = input_data.get("startUrls") or []
        if isinstance(start_urls, list) and start_urls:
            first = start_urls[0] or {}
            if isinstance(first, dict):
                return first.get("url")
    except Exception:
        pass
    return None


def _trim_start_urls(input_data: Dict[str, Any]) -> None:
    start_urls = input_data.get("startUrls") or []
    if not isinstance(start_urls, list):
        return

    try:
        max_sites = int(input_data.get("maxSites") or 10)
    except Exception:
        max_sites = 10

    max_sites = max(1, min(10000, max_sites))

    if len(start_urls) > max_sites:
        Actor.log.warning(
            f"Trimming startUrls from {len(start_urls)} to maxSites={max_sites}"
        )
        input_data["startUrls"] = start_urls[:max_sites]


def _dev_fingerprint() -> None:
    # Only do this locally (avoid noise in cloud)
    if os.getenv("APIFY_IS_AT_HOME") is not None:
        return
    try:
        p = Path(__file__)
        sha = hashlib.sha256(p.read_bytes()).hexdigest()[:12]
        line_count = sum(1 for _ in p.open("r", encoding="utf-8"))
        print(f">>> DEV_FINGERPRINT sha12={sha} lines={line_count}")
    except Exception as ex:
        print(f">>> DEV_FINGERPRINT failed: {ex}")


async def _export_outputs(input_data: Dict[str, Any], results: List[Dict[str, Any]]) -> None:
    """
    Reliable export independent of Dataset.export_to():
    - KV store: OUTPUT.csv, OUTPUT.xlsx
    - Disk saving OPTIONAL via saveToDisk=true (default false)
    """
    output_csv = bool(input_data.get("outputCsv", True))
    output_xlsx = bool(input_data.get("outputXlsx", True))
    save_to_disk = bool(input_data.get("saveToDisk", False))  # default KV-only

    if not (output_csv or output_xlsx):
        Actor.log.info("Export disabled (outputCsv/outputXlsx are false).")
        return

    out_dir = Path.cwd() / "output"
    if save_to_disk:
        out_dir.mkdir(parents=True, exist_ok=True)

    if output_csv:
        csv_bytes = _make_csv_bytes(results)
        await Actor.set_value("OUTPUT.csv", csv_bytes, content_type="text/csv")
        if save_to_disk:
            (out_dir / "OUTPUT.csv").write_bytes(csv_bytes)
            Actor.log.info(f"Saved OUTPUT.csv to KV + disk: {out_dir / 'OUTPUT.csv'}")
        else:
            Actor.log.info("Saved OUTPUT.csv to KV store (disk disabled).")

    if output_xlsx:
        xlsx_bytes = _make_xlsx_bytes(results)
        await Actor.set_value(
            "OUTPUT.xlsx",
            xlsx_bytes,
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        if save_to_disk:
            (out_dir / "OUTPUT.xlsx").write_bytes(xlsx_bytes)
            Actor.log.info(f"Saved OUTPUT.xlsx to KV + disk: {out_dir / 'OUTPUT.xlsx'}")
        else:
            Actor.log.info("Saved OUTPUT.xlsx to KV store (disk disabled).")


async def _amain() -> None:
    print(">>> _amain() entered")  # hard proof _amain is called

    # Ensure local storage dir is set for LOCAL runs
    if os.getenv("APIFY_LOCAL_STORAGE_DIR") is None and os.getenv("APIFY_IS_AT_HOME") is None:
        os.environ["APIFY_LOCAL_STORAGE_DIR"] = os.path.join(os.getcwd(), "apify_storage")

    async with Actor:
        Actor.log.info(">>> Actor context started")

        input_data: Dict[str, Any] = await Actor.get_input() or {}
        Actor.log.info(f"Actor.get_input() keys: {list(input_data.keys())}")

        # Local fallback (developer convenience)
        if (not input_data) or (not input_data.get("startUrls")):
            try:
                p = Path("local_input.json")
                Actor.log.info(f"Attempting to load local input from: {p.resolve()}")
                input_data = json.loads(p.read_text(encoding="utf-8"))
                Actor.log.info("Loaded local_input.json for local run")
            except Exception as ex:
                Actor.log.exception(
                    f"Failed to load local_input.json, using empty input. Reason: {ex}"
                )
                input_data = {}

        _trim_start_urls(input_data)
        _dev_fingerprint()

        Actor.log.info(f"FINAL input startUrls count: {len(input_data.get('startUrls') or [])}")
        Actor.log.info(f"APIFY_LOCAL_STORAGE_DIR={os.environ.get('APIFY_LOCAL_STORAGE_DIR')}")
        Actor.log.info(f"PWD={Path.cwd()}")

        push_empty = bool(input_data.get("pushEmptyRecord", False))

        try:
            # ------------------------------------------------------------
            # FAST MODE (optional): concurrent per-website processing
            # Requires: src.core.run_one_site(url, config, client) -> dict
            # Fallbacks to run_core() if not available.
            # ------------------------------------------------------------
            use_concurrent = bool(input_data.get("useConcurrent", False))
            results: List[Dict[str, Any]] = []

            if use_concurrent:
                try:
                    import httpx

                    from src.core import run_one_site  # must be implemented in src/core.py

                    def _normalize_start_urls(data: Dict[str, Any]) -> List[str]:
                        out: List[str] = []
                        for x in (data.get("startUrls") or []):
                            if isinstance(x, dict) and x.get("url"):
                                out.append(str(x["url"]))
                            elif isinstance(x, str):
                                out.append(x)
                        return out

                    urls = _normalize_start_urls(input_data)

                    concurrency = int(input_data.get("concurrency") or 20)
                    concurrency = max(1, min(200, concurrency))

                    per_site_timeout = float(input_data.get("siteTimeoutSec") or 25.0)
                    per_site_timeout = max(5.0, min(120.0, per_site_timeout))

                    sem = asyncio.Semaphore(concurrency)

                    timeout = httpx.Timeout(per_site_timeout, connect=10.0)
                    limits = httpx.Limits(
                        max_connections=concurrency * 2,
                        max_keepalive_connections=concurrency,
                    )

                    async with httpx.AsyncClient(
                        timeout=timeout,
                        limits=limits,
                        follow_redirects=True,
                        headers={"User-Agent": "Mozilla/5.0 (compatible; ContactExtractor/1.0)"},
                    ) as client:

                        async def _task(url: str) -> Optional[Dict[str, Any]]:
                            async with sem:
                                try:
                                    return await run_one_site(url, input_data, client)
                                except Exception as e:
                                    # per-site failure becomes a FAILED row (keeps run alive)
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

                        Actor.log.info(
                            f"[FAST] Concurrent mode ON: urls={len(urls)} "
                            f"concurrency={concurrency} siteTimeoutSec={per_site_timeout}"
                        )

                        tasks = [asyncio.create_task(_task(u)) for u in urls]
                        for coro in asyncio.as_completed(tasks):
                            r = await coro
                            if r and isinstance(r, dict):
                                results.append(_force_jsonable(r))

                    Actor.log.info(f"[FAST] Concurrent mode produced {len(results)} items")

                except ImportError:
                    Actor.log.warning(
                        "[FAST] useConcurrent=true but src.core.run_one_site not found. "
                        "Falling back to run_core()."
                    )
                    results = run_core(input_data) or []
                except Exception as ex:
                    Actor.log.exception(f"[FAST] Concurrent mode failed; falling back to run_core(). Reason: {ex}")
                    results = run_core(input_data) or []
            else:
                results = run_core(input_data) or []

            Actor.log.info(f"Core returned {len(results)} items")

            if not results:
                Actor.log.warning("No results returned by core processing")

                if push_empty:
                    input_url = _get_first_url(input_data) or "unknown"
                    empty = build_result(
                        input_url=input_url,
                        final_url=input_url,
                        best_email=None,
                        company_name=None,
                        best_phone=None,
                        emails=[],
                        phones=[],
                        socials={},
                        evidence=[],
                        contact_page=None,
                        address_text=None,
                        status_override="EMPTY",
                        error="No results returned by core processing",
                    )
                    await Actor.push_data(_force_jsonable(empty))
                    Actor.log.warning("Pushed one EMPTY record for visibility (pushEmptyRecord=true).")

                await _export_outputs(input_data, [])
                return

            # Batch push (JSON-safe)
            CHUNK_SIZE = 50
            batch: List[Dict[str, Any]] = []
            for item in results:
                if not item or not isinstance(item, dict):
                    continue
                batch.append(_force_jsonable(item))
                if len(batch) >= CHUNK_SIZE:
                    await Actor.push_data(batch)
                    batch.clear()
            if batch:
                await Actor.push_data(batch)

            await _export_outputs(input_data, results)

        except Exception as e:
            input_url = _get_first_url(input_data) or "unknown"
            failed = build_result(
                input_url=input_url,
                final_url=input_url,
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
            await Actor.push_data(_force_jsonable(failed))
            Actor.log.exception(f"Run failed, pushed FAILED record. Reason: {e}")


def main() -> None:
    print(">>> main() called")  # hard proof main is called
    asyncio.run(_amain())


if __name__ == "__main__":
    main()