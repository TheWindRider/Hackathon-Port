"""Pipeline runner: trigger BD scraper → poll → fetch → parse → upsert Port with OTel tracing.

Flow per platform:
  1. Trigger Bright Data Scraper Studio collector  → bd_collection_id (j_...)
  2. Upsert Port scraping_job with status="running"
  3. Poll BD until done                            → authoritative job metadata
  4. Fetch BD dataset                              → raw scraped records
  5. Parse records                                 → list[MarketRecord]
  6. Upsert Port scraping_job with final BD metadata (status, timestamps, count)
  7. Upsert each MarketRecord to Port prediction_market catalog

The bd_collection_id is BD's canonical job ID visible in the Scraper Studio portal
under Runs. It is stored on the Port scraping_job entity as bd_collection_id.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Literal

from opentelemetry import trace

from models.prediction_market import MarketRecord, ScrapeResult
from services.prediction_market import kalshi_scraper, polymarket_scraper
from services.software_factory import brightdata_client
from services.software_factory.port_client import (
    upsert_market_entity,
    upsert_scraping_job,
)
from services.telemetry import factory_step

logger = logging.getLogger(__name__)

Platform = Literal["kalshi", "polymarket", "both"]

# Fields tracked for data-quality / completeness reporting in SigNoz.
# Each tuple is (MarketRecord attribute name, human-readable field label for the dashboard).
_TRACKED_FIELDS: list[tuple[str, str]] = [
    ("current_yes_price", "yes_price"),
    ("current_no_price", "no_price"),
    ("volume_24h", "volume"),
    ("category", "category"),
    ("expiration_date", "expiration"),
]


def _emit_field_completeness(
    platform: str,
    records: list[MarketRecord],
) -> None:
    """Emit one child span per tracked field, each carrying:

      factory.platform   — "kalshi" or "polymarket"
      factory.field_name — field label (e.g. "yes_price", "volume")
      factory.fill_rate  — % of records where the field is non-null (0.0–100.0)
      factory.fill_count — raw count of non-null records
      factory.total      — total records in this batch

    Span name: "data_quality.field_fill_rate"

    Using one span per field (rather than numeric attributes on the parent span)
    means SigNoz can GROUP BY factory.field_name and factory.platform directly,
    making a proper categorical grouped bar chart possible.
    """
    n = len(records)
    tracer = trace.get_tracer(__name__)

    for field_attr, field_name in _TRACKED_FIELDS:
        count = sum(1 for r in records if getattr(r, field_attr, None) is not None)
        fill_rate = round(count / n * 100, 1) if n > 0 else 0.0

        with tracer.start_as_current_span("data_quality.field_fill_rate") as span:
            span.set_attribute("factory.platform", platform)
            span.set_attribute("factory.field_name", field_name)
            span.set_attribute("factory.fill_rate", fill_rate)
            span.set_attribute("factory.fill_count", count)
            span.set_attribute("factory.total", n)

        logger.debug(
            "%s field %s: %d / %d (%.1f%%)", platform, field_name, count, n, fill_rate
        )


def _run_platform(
    platform: Literal["kalshi", "polymarket"], limit: int
) -> ScrapeResult:
    """Run the full BD scrape + Port upsert pipeline for one platform.

    The scraping_job entity in Port is updated at three checkpoints:
      - immediately after trigger (status=running, bd_collection_id set)
      - after BD job completes (status updated from BD, timestamps from BD)
      - on error (status=failed)
    """
    scraper = kalshi_scraper if platform == "kalshi" else polymarket_scraper

    if not scraper.COLLECTOR_ID:
        raise RuntimeError(
            f"BRIGHTDATA_{platform.upper()}_COLLECTOR_ID is not set. "
            f"Run scripts/setup_bd_scrapers.py to create the collector."
        )

    # Stable Port entity ID for this run (platform + timestamp + short UUID)
    collector_id = (
        f"{platform}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}"
        f"-{uuid.uuid4().hex[:6]}"
    )
    result = ScrapeResult(
        platform=platform,
        collector_id=collector_id,
        started_at=datetime.now(timezone.utc),
    )

    try:
        # --- Step 1: Trigger BD Scraper Studio collector ---
        with factory_step(f"scrape.{platform}.trigger", collector_id=collector_id):
            bd_collection_id = brightdata_client.trigger_collection(
                scraper.COLLECTOR_ID, scraper.BROWSE_URL
            )
            result.bd_collection_id = bd_collection_id
            logger.info(
                "%s: triggered BD job %s (collector=%s)",
                platform,
                bd_collection_id,
                scraper.COLLECTOR_ID,
            )

        # --- Step 2: Register job as "running" in Port ---
        upsert_scraping_job(result.to_port_job_dict())

        # --- Step 3: Poll BD until done ---
        with factory_step(
            f"scrape.{platform}.poll",
            bd_collection_id=bd_collection_id,
        ):
            bd_meta = brightdata_client.poll_until_done(bd_collection_id)
            result.apply_bd_meta(bd_meta)
            logger.info(
                "%s: BD job done — status=%s lines=%s success=%s fails=%s",
                platform,
                bd_meta.get("status"),
                bd_meta.get("lines"),
                bd_meta.get("success"),
                bd_meta.get("fails"),
            )

        if result.bd_status == "failed":
            raise RuntimeError(f"BD job {bd_collection_id} reported status=failed")

        # --- Step 4: Fetch raw records from BD ---
        with factory_step(
            f"scrape.{platform}.fetch", bd_collection_id=bd_collection_id
        ):
            raw = brightdata_client.fetch_results(bd_collection_id)

        # --- Step 5: Parse into MarketRecord objects ---
        with factory_step(f"scrape.{platform}.parse", raw_count=len(raw)):
            records: list[MarketRecord] = scraper.parse_results(raw)[:limit]
            _emit_field_completeness(platform, records)

        result.records = records
        result.completed_at = datetime.now(timezone.utc)

        # --- Step 6: Update Port scraping_job with final BD metadata ---
        upsert_scraping_job(result.to_port_job_dict())

        # --- Step 7: Upsert each MarketRecord to Port ---
        with factory_step(f"port.upsert.{platform}", count=len(records)):
            ok, fail = 0, 0
            for rec in records:
                try:
                    upsert_market_entity(rec.to_port_dict())
                    ok += 1
                except Exception as exc:
                    fail += 1
                    logger.warning("Failed to upsert %s: %s", rec.identifier, exc)

            logger.info(
                "%s: upserted %d / %d records to Port (failed=%d)",
                platform,
                ok,
                len(records),
                fail,
            )

    except Exception as exc:
        result.error = str(exc)
        result.completed_at = datetime.now(timezone.utc)
        logger.error("%s scrape failed: %s", platform, exc, exc_info=True)
        upsert_scraping_job(result.to_port_job_dict())

    return result


def run(platform: Platform = "both", limit: int = 50) -> list[ScrapeResult]:
    """Run the full scrape → Port pipeline.

    Args:
        platform: 'kalshi', 'polymarket', or 'both'.
        limit:    max MarketRecord objects to upsert per platform.

    Returns:
        List of ScrapeResult (one per platform scraped).
    """
    platforms: list[Literal["kalshi", "polymarket"]] = (
        ["kalshi", "polymarket"] if platform == "both" else [platform]
    )

    results = []
    with factory_step("pipeline.run", platform=platform):
        for p in platforms:
            logger.info("Starting %s scrape (limit=%d)", p, limit)
            result = _run_platform(p, limit)
            results.append(result)
            logger.info(
                "%s done — %d records, status=%s, bd_job=%s",
                p,
                len(result.records),
                result.status,
                result.bd_collection_id,
            )

    return results
