"""Port.io client for upserting prediction market entities and scraping job records.

Uses the Port REST API with the same Bearer token as the MCP server.
Token is read from .devin/port_mcp_token.txt (written by refresh_port_token.sh).
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import httpx

_PORT_API = "https://api.getport.io/v1"
_TOKEN_FILE = Path(__file__).parents[2] / ".devin" / "port_mcp_token.txt"


def _token() -> str:
    """Read Bearer token from file or PORT_TOKEN env var."""
    env_token = os.environ.get("PORT_TOKEN")
    if env_token:
        return env_token
    if _TOKEN_FILE.exists():
        return _TOKEN_FILE.read_text().strip()
    raise RuntimeError(
        f"Port token not found. Run scripts/refresh_port_token.sh or set PORT_TOKEN env var."
    )


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {_token()}",
        "Content-Type": "application/json",
    }


def upsert_market_entity(market: dict) -> dict:
    """Upsert a prediction_market entity in Port.

    Args:
        market: dict with keys matching the prediction_market blueprint properties.
                Must include 'identifier', 'title', and 'platform'.

    Returns:
        Port API response dict.
    """
    identifier = market["identifier"]
    payload = {
        "identifier": identifier,
        "title": market["title"],
        "properties": {
            "ticker": market.get("ticker", identifier),
            "platform": market["platform"],
            "title": market["title"],
            "category": market.get("category"),
            "current_yes_price": market.get("current_yes_price"),
            "current_no_price": market.get("current_no_price"),
            "volume_24h": market.get("volume_24h"),
            "total_volume": market.get("total_volume"),
            "expiration_date": market.get("expiration_date"),
            "url": market.get("url"),
            "status": market.get("status", "active"),
            "last_scraped_at": datetime.now(timezone.utc).isoformat(),
        },
    }
    # Remove None values from properties
    payload["properties"] = {
        k: v for k, v in payload["properties"].items() if v is not None
    }

    with httpx.Client(timeout=30) as client:
        resp = client.post(
            f"{_PORT_API}/blueprints/prediction_market/entities?upsert=true",
            headers=_headers(),
            json=payload,
        )
        resp.raise_for_status()
        return resp.json()


def upsert_scraping_job(job: dict) -> dict:
    """Upsert a scraping_job entity in Port.

    Args:
        job: dict with keys: identifier, platform, status, collector_id,
             bd_collection_id (optional BD portal job ID), started_at,
             completed_at (optional), records_scraped (optional),
             error_message (optional).

    Returns:
        Port API response dict.
    """
    payload = {
        "identifier": job["identifier"],
        "title": f"{job['platform'].capitalize()} scrape {job['identifier']}",
        "properties": {
            "platform": job["platform"],
            "status": job["status"],
            "collector_id": job.get("collector_id"),
            "bd_collection_id": job.get("bd_collection_id"),
            "started_at": job.get("started_at"),
            "completed_at": job.get("completed_at"),
            "records_scraped": job.get("records_scraped"),
            "error_message": job.get("error_message"),
        },
    }
    payload["properties"] = {
        k: v for k, v in payload["properties"].items() if v is not None
    }

    with httpx.Client(timeout=30) as client:
        resp = client.post(
            f"{_PORT_API}/blueprints/scraping_job/entities?upsert=true",
            headers=_headers(),
            json=payload,
        )
        resp.raise_for_status()
        return resp.json()
