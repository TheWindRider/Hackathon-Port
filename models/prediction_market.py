"""Pydantic models for scraped prediction market data."""

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


class MarketRecord(BaseModel):
    """A single prediction market scraped from Kalshi or Polymarket."""

    identifier: str = Field(
        description="Unique stable ID used as Port entity identifier"
    )
    ticker: str = Field(description="Platform-native ticker or slug")
    platform: Literal["kalshi", "polymarket"]
    title: str
    category: Optional[str] = None
    current_yes_price: Optional[float] = Field(
        None, ge=0, le=1, description="Probability 0–1"
    )
    current_no_price: Optional[float] = Field(None, ge=0, le=1)
    volume_24h: Optional[float] = Field(None, ge=0)
    total_volume: Optional[float] = Field(None, ge=0)
    expiration_date: Optional[datetime] = None
    url: str
    status: Literal["active", "closed", "suspended"] = "active"

    def to_port_dict(self) -> dict:
        """Convert to the dict shape expected by port_client.upsert_market_entity."""
        d = self.model_dump()
        if self.expiration_date:
            d["expiration_date"] = self.expiration_date.isoformat()
        return d


class ScrapeResult(BaseModel):
    """Result of a single platform scrape run, including BD Scraper Studio job metadata."""

    platform: Literal["kalshi", "polymarket", "both"]
    collector_id: str  # our job identifier (used as Port entity ID)
    started_at: datetime  # local time when we triggered the BD job
    completed_at: Optional[datetime] = None
    records: list[MarketRecord] = Field(default_factory=list)
    error: Optional[str] = None

    # Bright Data Scraper Studio authoritative job metadata
    # (populated after poll_until_done completes)
    bd_collection_id: Optional[str] = None  # j_... job ID visible in BD portal
    bd_status: Optional[str] = None  # "done" | "failed" | "cancelled"
    bd_lines: Optional[int] = None  # total records returned by BD
    bd_success: Optional[int] = None  # successful input URLs
    bd_fails: Optional[int] = None  # failed input URLs
    bd_started_at: Optional[datetime] = None  # when BD started running (from log)
    bd_finished_at: Optional[datetime] = None  # when BD finished (from log)

    @property
    def status(self) -> Literal["running", "success", "failed"]:
        if self.error:
            return "failed"
        if self.bd_status == "failed":
            return "failed"
        if self.completed_at:
            return "success"
        return "running"

    def apply_bd_meta(self, bd_meta: dict) -> None:
        """Populate BD metadata fields from a /dca/log response dict."""
        self.bd_status = bd_meta.get("status")
        self.bd_lines = bd_meta.get("lines")
        self.bd_success = bd_meta.get("success")
        self.bd_fails = bd_meta.get("fails")

        started = bd_meta.get("started")
        if started:
            try:
                self.bd_started_at = datetime.fromisoformat(
                    str(started).replace("Z", "+00:00")
                )
            except (ValueError, AttributeError):
                pass

        finished = bd_meta.get("finished")
        if finished:
            try:
                self.bd_finished_at = datetime.fromisoformat(
                    str(finished).replace("Z", "+00:00")
                )
            except (ValueError, AttributeError):
                pass

    def to_port_job_dict(self) -> dict:
        """Serialize to the shape expected by port_client.upsert_scraping_job.

        Prefers BD authoritative timestamps and record counts when available.
        Falls back to local measurements.
        """
        started = (
            self.bd_started_at.isoformat()
            if self.bd_started_at
            else self.started_at.isoformat()
        )
        completed = (
            self.bd_finished_at.isoformat()
            if self.bd_finished_at
            else (self.completed_at.isoformat() if self.completed_at else None)
        )
        record_count = self.bd_lines if self.bd_lines is not None else len(self.records)

        return {
            "identifier": self.collector_id,
            "platform": self.platform,
            "status": self.status,
            "collector_id": self.collector_id,
            "bd_collection_id": self.bd_collection_id,
            "started_at": started,
            "completed_at": completed,
            "records_scraped": record_count,
            "error_message": self.error,
        }
