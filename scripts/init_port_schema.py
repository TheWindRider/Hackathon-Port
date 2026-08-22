#!/usr/bin/env python3
"""Initialize Port.io schema for the Agentic Software Factory hackathon project.

Idempotently upserts:
  - prediction_market blueprint
  - scraping_job blueprint
  - data_freshness scorecard on prediction_market
  - run_market_scrape self-service action

Uses the Port REST API directly (same token as the MCP server).
Run this once per environment, or re-run safely — all operations are upserts.

Usage:
    uv run python scripts/init_port_schema.py
"""

import json
import os
import sys
from pathlib import Path

import httpx

PORT_API = "https://api.getport.io/v1"
TOKEN_FILE = Path(__file__).parents[1] / ".devin" / "port_mcp_token.txt"


def get_token() -> str:
    token = os.environ.get("PORT_TOKEN")
    if token:
        return token
    if TOKEN_FILE.exists():
        return TOKEN_FILE.read_text().strip()
    sys.exit(
        "Error: Port token not found.\n"
        "Run scripts/refresh_port_token.sh or set PORT_TOKEN env var."
    )


def headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def upsert(client: httpx.Client, method: str, url: str, payload: dict, label: str) -> dict:
    resp = client.request(method, url, json=payload)
    if resp.status_code in (200, 201):
        print(f"  ok  {label}")
        return resp.json()
    # 409 = already exists with same content — treat as ok
    if resp.status_code == 409:
        print(f"  --  {label} (already up-to-date)")
        return resp.json()
    print(f"  !!  {label} — HTTP {resp.status_code}: {resp.text[:200]}", file=sys.stderr)
    resp.raise_for_status()


# ---------------------------------------------------------------------------
# Blueprint definitions
# ---------------------------------------------------------------------------

PREDICTION_MARKET_BLUEPRINT = {
    "identifier": "prediction_market",
    "title": "Prediction Market",
    "description": "A public prediction market tracked from Kalshi or Polymarket",
    "icon": "Boxes",
    "schema": {
        "properties": {
            "ticker": {"title": "Ticker", "type": "string", "description": "Unique market ticker or slug"},
            "platform": {
                "title": "Platform",
                "type": "string",
                "enum": ["kalshi", "polymarket"],
                "enumColors": {"kalshi": "blue", "polymarket": "purple"},
            },
            "title": {"title": "Market Title", "type": "string"},
            "category": {"title": "Category", "type": "string"},
            "current_yes_price": {"title": "YES Price", "type": "number"},
            "current_no_price": {"title": "NO Price", "type": "number"},
            "volume_24h": {"title": "24h Volume ($)", "type": "number"},
            "total_volume": {"title": "Total Volume ($)", "type": "number"},
            "expiration_date": {"title": "Expiration Date", "type": "string", "format": "date-time"},
            "url": {"title": "Market URL", "type": "string", "format": "url"},
            "status": {
                "title": "Status",
                "type": "string",
                "enum": ["active", "closed", "suspended"],
                "enumColors": {"active": "green", "closed": "darkGray", "suspended": "orange"},
            },
            "last_scraped_at": {"title": "Last Scraped At", "type": "string", "format": "date-time"},
        },
        "required": ["ticker", "platform", "title"],
    },
    "calculationProperties": {
        "hours_since_scrape": {
            "title": "Hours Since Scrape",
            "type": "number",
            "calculation": (
                'if (.properties.last_scraped_at != null) then '
                '((now / 3600) - (.properties.last_scraped_at | '
                r'capture("(?<date>\\d{4}-\\d{2}-\\d{2}T\\d{2})") | '
                '.date | strptime("%Y-%m-%dT%H") | mktime / 3600)) | floor '
                "else 999 end"
            ),
        },
        "is_fresh": {
            "title": "Is Fresh",
            "type": "boolean",
            "calculation": (
                "if (.properties.last_scraped_at != null) then "
                "((now - (.properties.last_scraped_at | fromdateiso8601)) < 3600) "
                "else false end"
            ),
            "colorized": True,
            "colors": {"true": "green", "false": "red"},
        },
    },
}

SCRAPING_JOB_BLUEPRINT = {
    "identifier": "scraping_job",
    "title": "Scraping Job",
    "description": "A single scraping run against a prediction market platform",
    "icon": "RefreshCw",
    "schema": {
        "properties": {
            "platform": {
                "title": "Platform",
                "type": "string",
                "enum": ["kalshi", "polymarket", "both"],
                "enumColors": {"kalshi": "blue", "polymarket": "purple", "both": "turquoise"},
            },
            "status": {
                "title": "Status",
                "type": "string",
                "enum": ["running", "success", "failed"],
                "enumColors": {"running": "yellow", "success": "green", "failed": "red"},
            },
            "collector_id": {"title": "Collector ID", "type": "string"},
            "started_at": {"title": "Started At", "type": "string", "format": "date-time"},
            "completed_at": {"title": "Completed At", "type": "string", "format": "date-time"},
            "records_scraped": {"title": "Records Scraped", "type": "number"},
            "error_message": {"title": "Error Message", "type": "string"},
        },
        "required": ["platform", "status"],
    },
}

# ---------------------------------------------------------------------------
# Scorecard definition
# ---------------------------------------------------------------------------

DATA_FRESHNESS_SCORECARD = {
    "identifier": "data_freshness",
    "title": "Data Freshness",
    "levels": [
        {"color": "red", "title": "Basic"},
        {"color": "bronze", "title": "Bronze"},
    ],
    "rules": [
        {
            "identifier": "is_fresh_rule",
            "title": "Market data scraped within the last hour",
            "level": "Bronze",
            "query": {
                "combinator": "and",
                "conditions": [
                    {"operator": "=", "property": "is_fresh", "value": "true"},
                ],
            },
        }
    ],
}

# ---------------------------------------------------------------------------
# Self-service action definition
# ---------------------------------------------------------------------------

RUN_MARKET_SCRAPE_ACTION = {
    "identifier": "run_market_scrape",
    "title": "Run Market Scrape",
    "description": "Trigger a prediction market scrape for Kalshi and/or Polymarket",
    "icon": "RefreshCw",
    "trigger": {
        "type": "self-service",
        "operation": "DAY-2",
        "blueprintIdentifier": "prediction_market",
        "userInputs": {
            "properties": {
                "platform": {
                    "type": "string",
                    "title": "Platform",
                    "description": "Which platform to scrape",
                    "enum": ["kalshi", "polymarket", "both"],
                    "default": "both",
                }
            }
        },
    },
    "invocationMethod": {
        "type": "WEBHOOK",
        "url": "http://localhost:8000/actions/run_market_scrape",
    },
}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    token = get_token()
    h = headers(token)

    with httpx.Client(base_url=PORT_API, headers=h, timeout=30) as client:
        print("\n=== Blueprints ===")
        upsert(client, "POST", "/blueprints", PREDICTION_MARKET_BLUEPRINT, "prediction_market blueprint")
        upsert(client, "POST", "/blueprints", SCRAPING_JOB_BLUEPRINT, "scraping_job blueprint")

        print("\n=== Scorecard ===")
        upsert(
            client,
            "POST",
            "/blueprints/prediction_market/scorecards",
            DATA_FRESHNESS_SCORECARD,
            "data_freshness scorecard",
        )

        print("\n=== Self-Service Action ===")
        upsert(client, "POST", "/actions", RUN_MARKET_SCRAPE_ACTION, "run_market_scrape action")

    print("\nPort schema initialization complete.")


if __name__ == "__main__":
    main()
