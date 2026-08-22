"""Polymarket market scraper using Bright Data Scraper Studio (browser scraping only).

Strategy: BD Scraper Studio collector visits https://polymarket.com/markets and
returns what is visible on the listing page — titles, volumes, URLs, and a
generic category. Prices (yes_price / no_price) are NOT available on the listing
page and are intentionally left absent.

This limited field set is the natural result of what a browser scraper can see
on the Polymarket markets listing — and is the starting point for a SigNoz
observability story comparing field completeness across platforms.

Collector: BRIGHTDATA_POLYMARKET_COLLECTOR_ID (default: c_mt4uge6h12nwh5l4rc)
"""

import logging
import os
import re
from typing import Optional

from models.prediction_market import MarketRecord

logger = logging.getLogger(__name__)

_POLYMARKET_BASE = "https://polymarket.com"
BROWSE_URL = "https://polymarket.com/markets"

# Scraper Studio collector ID (created via: bdata scraper create polymarket.com/markets ...)
COLLECTOR_ID: str = os.environ.get(
    "BRIGHTDATA_POLYMARKET_COLLECTOR_ID", "c_mt4uge6h12nwh5l4rc"
)


def _parse_volume_str(val) -> Optional[float]:
    """Parse BD volume string like '$3.65M Vol.' or '$777.32K Vol.' into float."""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).replace("$", "").replace(",", "").strip()
    s = re.sub(r"\s*(vol\.?|volume).*", "", s, flags=re.IGNORECASE).strip()
    multiplier = 1.0
    if s.endswith("M"):
        multiplier = 1_000_000
        s = s[:-1]
    elif s.endswith("K"):
        multiplier = 1_000
        s = s[:-1]
    elif s.endswith("B"):
        multiplier = 1_000_000_000
        s = s[:-1]
    try:
        return float(s) * multiplier
    except (ValueError, TypeError):
        return None


def _slug_from_url(market_url: str) -> str:
    """Extract event slug from a Polymarket event URL."""
    parts = [p for p in market_url.rstrip("/").split("/") if p]
    return parts[-1] if parts else re.sub(r"[^a-z0-9-]", "-", market_url.lower())[:80]


def parse_results(raw: list[dict]) -> list[MarketRecord]:
    """Parse Bright Data Scraper Studio results into MarketRecord list.

    Each raw record has the shape returned by the polymarket-browse collector:
      {
        "market_title": str,
        "total_volume": str,   # e.g. "$3.65M Vol." — may be absent
        "category": str,       # usually "Sports" from BD listing page
        "market_url": str,
        "input": {"url": str}
      }

    Intentionally missing fields (not available on the Polymarket listing page):
      - current_yes_price   (requires clicking into each market)
      - current_no_price    (requires clicking into each market)
      - expiration_date     (not shown on listing)

    These gaps are instrumented as OTel span attributes in runner.py so they
    show up as a data quality signal in SigNoz alongside the Kalshi comparison.

    Args:
        raw: list of dicts returned by brightdata_client.fetch_results()

    Returns:
        list of MarketRecord objects (prices will always be None)
    """
    records: list[MarketRecord] = []
    seen_slugs: set[str] = set()

    for item in raw:
        market_url = item.get("market_url") or item.get("product_page_url", "")
        if not market_url:
            logger.debug("Skipping record with no market_url: %s", item)
            continue

        slug = _slug_from_url(market_url)
        if slug in seen_slugs:
            continue
        seen_slugs.add(slug)

        identifier = f"polymarket-{slug[:80]}"
        ticker = slug[:100]

        title = str(item.get("market_title") or "").strip()
        if not title:
            logger.debug("Skipping record with empty title: %s", item)
            continue

        volume = _parse_volume_str(item.get("total_volume") or item.get("volume_24h"))
        category = item.get("category")

        # Prices are intentionally absent — BD listing page does not expose them
        try:
            records.append(
                MarketRecord(
                    identifier=identifier,
                    ticker=ticker,
                    platform="polymarket",
                    title=title[:200],
                    category=category,
                    current_yes_price=None,  # not available on listing page
                    current_no_price=None,  # not available on listing page
                    volume_24h=volume,
                    url=market_url,
                    status="active",
                )
            )
        except Exception as exc:
            logger.debug("Skipping malformed Polymarket record %s: %s", identifier, exc)

    logger.info("Polymarket parse_results: %d / %d records", len(records), len(raw))
    return records
