from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import requests


@dataclass
class ApifyRun:
    id: str
    status: str
    default_dataset_id: Optional[str] = None
    actor_id: Optional[str] = None
    started_at: Optional[str] = None
    finished_at: Optional[str] = None


class ApifyClientLite:
    """
    Minimal Apify API wrapper:
    - start actor run
    - poll run status
    - fetch dataset items
    """

    def __init__(self, token: str, base_url: str = "https://api.apify.com/v2"):
        if not token:
            raise ValueError("Apify token is required.")
        self.token = token
        self.base_url = base_url.rstrip("/")

    def _url(self, path: str) -> str:
        if not path.startswith("/"):
            path = "/" + path
        return f"{self.base_url}{path}"

    def start_actor_run(self, actor_id: str, input_payload: Dict[str, Any], timeout_secs: int = 60) -> ApifyRun:
        """
        Start actor run:
        POST /acts/{actorId}/runs
        """
        if not actor_id:
            raise ValueError("actor_id is required.")
        url = self._url(f"/acts/{actor_id}/runs")
        params = {"token": self.token}
        r = requests.post(url, params=params, json=input_payload, timeout=timeout_secs)
        r.raise_for_status()
        data = r.json().get("data", {})  # Apify returns {"data": {...}}
        return ApifyRun(
            id=data.get("id"),
            status=data.get("status"),
            default_dataset_id=data.get("defaultDatasetId"),
            actor_id=data.get("actId"),
            started_at=data.get("startedAt"),
            finished_at=data.get("finishedAt"),
        )

    def get_run(self, run_id: str, timeout_secs: int = 60) -> ApifyRun:
        """
        GET /actor-runs/{runId}
        """
        url = self._url(f"/actor-runs/{run_id}")
        params = {"token": self.token}
        r = requests.get(url, params=params, timeout=timeout_secs)
        r.raise_for_status()
        data = r.json().get("data", {})
        return ApifyRun(
            id=data.get("id"),
            status=data.get("status"),
            default_dataset_id=data.get("defaultDatasetId"),
            actor_id=data.get("actId"),
            started_at=data.get("startedAt"),
            finished_at=data.get("finishedAt"),
        )

    def wait_for_finish(
        self,
        run_id: str,
        poll_seconds: float = 3.0,
        max_wait_seconds: int = 20 * 60,
    ) -> ApifyRun:
        """
        Poll until run is SUCCEEDED/FAILED/TIMED-OUT/ABORTED.
        """
        terminal = {"SUCCEEDED", "FAILED", "TIMED-OUT", "ABORTED"}
        start = time.time()

        last = self.get_run(run_id)
        while last.status not in terminal:
            if time.time() - start > max_wait_seconds:
                raise TimeoutError(f"Run did not finish within {max_wait_seconds} seconds. Last status={last.status}")
            time.sleep(poll_seconds)
            last = self.get_run(run_id)
        return last

    def list_dataset_items(
        self,
        dataset_id: str,
        limit: int = 1000,
        offset: int = 0,
        clean: bool = True,
        timeout_secs: int = 60,
    ) -> List[Dict[str, Any]]:
        """
        GET /datasets/{datasetId}/items
        Use clean=true to return JSON objects without metadata wrappers.
        """
        if not dataset_id:
            raise ValueError("dataset_id is required.")

        url = self._url(f"/datasets/{dataset_id}/items")
        params = {
            "token": self.token,
            "limit": limit,
            "offset": offset,
            "clean": "true" if clean else "false",
            "format": "json",
        }
        r = requests.get(url, params=params, timeout=timeout_secs)
        r.raise_for_status()
        return r.json()  # clean=true returns list[dict]

    def list_all_dataset_items(self, dataset_id: str, page_size: int = 1000) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        offset = 0
        while True:
            batch = self.list_dataset_items(dataset_id=dataset_id, limit=page_size, offset=offset, clean=True)
            if not batch:
                break
            out.extend(batch)
            if len(batch) < page_size:
                break
            offset += page_size
        return out