"""Bright Data Scraper Studio Collection API client.

Wraps the three-step flow for running a Scraper Studio collector:
  1. trigger_collection  → POST /dca/trigger     → collection_id (j_...)
  2. poll_until_done     → GET  /dca/log/{id}    → job metadata dict
  3. fetch_results       → GET  /dca/dataset?id  → list of scraped records

The collection_id (j_...) is Bright Data's authoritative job ID that appears
in the portal under Scraper Studio → Runs.
"""

import logging
import os
import time

import httpx

logger = logging.getLogger(__name__)

_BASE = "https://api.brightdata.com"
_API_KEY = os.environ.get("BRIGHTDATA_API_KEY", "")

# Status values returned by /dca/log
_TERMINAL_STATUSES = {"done", "failed", "cancelled"}


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {_API_KEY}",
        "Content-Type": "application/json",
    }


def trigger_collection(collector_id: str, url: str) -> str:
    """Trigger a Scraper Studio collector run for a single URL.

    POST /dca/trigger?collector=<id>&queue_next=1
    Body: [{"url": "<url>"}]

    Args:
        collector_id: The c_... Scraper Studio collector ID.
        url:          The target URL to pass as the run input.

    Returns:
        collection_id (j_...) — the BD job ID for this run.
    """
    endpoint = f"{_BASE}/dca/trigger?collector={collector_id}&queue_next=1"
    with httpx.Client(timeout=30) as client:
        resp = client.post(endpoint, headers=_headers(), json=[{"url": url}])
        resp.raise_for_status()
        data = resp.json()

    collection_id = data.get("collection_id") or data.get("id")
    if not collection_id:
        raise RuntimeError(f"BD trigger response missing collection_id: {data}")

    logger.info(
        "Triggered BD collector %s → collection_id=%s", collector_id, collection_id
    )
    return collection_id


def poll_until_done(
    collection_id: str,
    poll_interval: float = 5.0,
    timeout_s: int = 300,
) -> dict:
    """Poll /dca/log/{collection_id} until the job reaches a terminal status.

    Args:
        collection_id: The j_... BD job ID returned by trigger_collection.
        poll_interval:  Seconds between polls (default 5s).
        timeout_s:      Maximum seconds to wait before raising TimeoutError.

    Returns:
        Final log dict with keys:
          id, status, lines, success, fails, created, started, finished, ...

    Raises:
        TimeoutError: if job doesn't finish within timeout_s.
        RuntimeError: if BD returns an error status.
    """
    endpoint = f"{_BASE}/dca/log/{collection_id}"
    deadline = time.monotonic() + timeout_s
    attempt = 0

    while True:
        attempt += 1
        with httpx.Client(timeout=30) as client:
            resp = client.get(endpoint, headers=_headers())
            resp.raise_for_status()
            data = resp.json()

        status = data.get("status", "")
        logger.debug(
            "BD poll %d: collection_id=%s status=%s lines=%s",
            attempt,
            collection_id,
            status,
            data.get("lines"),
        )

        if status in _TERMINAL_STATUSES:
            logger.info(
                "BD job %s finished: status=%s lines=%s success=%s fails=%s",
                collection_id,
                status,
                data.get("lines"),
                data.get("success"),
                data.get("fails"),
            )
            return data

        if time.monotonic() > deadline:
            raise TimeoutError(
                f"BD job {collection_id} did not complete within {timeout_s}s "
                f"(last status: {status!r})"
            )

        time.sleep(poll_interval)


def fetch_results(collection_id: str) -> list[dict]:
    """Fetch the scraped records for a completed BD job.

    GET /dca/dataset?id={collection_id}

    Args:
        collection_id: The j_... BD job ID.

    Returns:
        List of raw scraped record dicts as returned by the collector.

    Raises:
        RuntimeError: if BD returns a non-list (e.g. still building).
    """
    endpoint = f"{_BASE}/dca/dataset?id={collection_id}"
    with httpx.Client(timeout=60) as client:
        resp = client.get(endpoint, headers=_headers())
        resp.raise_for_status()
        data = resp.json()

    if not isinstance(data, list):
        raise RuntimeError(
            f"BD dataset for {collection_id} returned unexpected shape: {type(data).__name__}"
        )

    logger.info("BD dataset fetched: %d records for %s", len(data), collection_id)
    return data
