"""Kalshi market scraper using Bright Data Scraper Studio.

Strategy: trigger the Kalshi browser scraper (Scraper Studio collector) via the
BD Collection API, then parse the returned records into MarketRecord objects.

The scraper visits https://kalshi.com/browse and extracts market listings
including prices, volumes, categories, and URLs.

Collector: BRIGHTDATA_KALSHI_COLLECTOR_ID (default: c_mt4ucalol8f6d1rhd)
"""

import logging
import os
import re
from typing import Optional

from models.prediction_market import MarketRecord

logger = logging.getLogger(__name__)

_KALSHI_BASE = "https://kalshi.com"
BROWSE_URL = "https://kalshi.com/browse"

# Scraper Studio collector ID (created via: bdata scraper create kalshi.com/browse ...)
COLLECTOR_ID: str = os.environ.get(
    "BRIGHTDATA_KALSHI_COLLECTOR_ID", "c_mt4ucalol8f6d1rhd"
)


def _parse_price(val) -> Optional[float]:
    """Parse a price value into 0-1 probability."""
    if val is None:
        return None
    try:
        f = float(val)
        return round(f if f <= 1 else f / 100, 4)
    except (ValueError, TypeError):
        return None


def _slug_from_url(market_url: str) -> str:
    """Extract a stable slug from a Kalshi market URL for use as identifier."""
    # e.g. https://kalshi.com/markets/kxbtcd/bitcoin-price-abovebelow/kxbtcd-26aug2217
    # → kxbtcd-26aug2217
    parts = [p for p in market_url.rstrip("/").split("/") if p]
    return parts[-1] if parts else re.sub(r"[^a-z0-9-]", "-", market_url.lower())[:80]


def parse_results(raw: list[dict]) -> list[MarketRecord]:
    """Parse Bright Data Scraper Studio results into MarketRecord list.

    Each raw record has the shape returned by the kalshi-browse collector:
      {
        "market_title": str,
        "yes_price": float,   # 0-1 probability
        "no_price": float,    # 0-1 probability
        "volume_24h": int,    # dollar volume
        "category": str,
        "market_url": str,
        "input": {"url": str}
      }

    Args:
        raw: list of dicts returned by brightdata_client.fetch_results()

    Returns:
        list of MarketRecord objects
    """
    records: list[MarketRecord] = []
    for item in raw:
        market_url = item.get("market_url") or item.get("product_page_url", "")
        if not market_url:
            logger.debug("Skipping record with no market_url: %s", item)
            continue

        slug = _slug_from_url(market_url)
        identifier = f"kalshi-{slug}"[:100]
        ticker = slug[:100]

        title = str(item.get("market_title") or "").strip()
        # BD scraper sometimes duplicates title ("Foo Foo") — deduplicate
        half = len(title) // 2
        if half > 0 and title[:half].strip() == title[half:].strip():
            title = title[:half].strip()
        if not title:
            logger.debug("Skipping record with empty title: %s", item)
            continue

        yes_price = _parse_price(item.get("yes_price"))
        no_price = _parse_price(item.get("no_price"))
        volume = item.get("volume_24h")
        volume = float(volume) if volume is not None else None
        category = item.get("category")

        try:
            records.append(
                MarketRecord(
                    identifier=identifier,
                    ticker=ticker,
                    platform="kalshi",
                    title=title[:200],
                    category=category,
                    current_yes_price=yes_price,
                    current_no_price=no_price,
                    volume_24h=volume,
                    url=market_url,
                    status="active",
                )
            )
        except Exception as exc:
            logger.debug("Skipping malformed Kalshi record %s: %s", identifier, exc)

    logger.info("Kalshi parse_results: %d / %d records", len(records), len(raw))
    return records
