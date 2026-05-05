"""US Treasury Auction Results collector.

Wires fiscaldata.treasury.gov "Treasury Securities Auctions Data"
dataset into Ichor's macro context. Public, no auth, JSON.

Endpoint (verified 2026-05-05) :
  GET https://api.fiscaldata.treasury.gov/services/api/fiscal_service
        /v1/accounting/od/securities_auctions
      ?fields=record_date,issue_date,security_type,security_term,
              high_yield,bid_to_cover_ratio
      &filter=issue_date:gte:{from_date}
      &sort=-issue_date&page[size]=200

Source:
  - https://fiscaldata.treasury.gov/datasets/treasury-securities-auctions-data/
  - https://fiscaldata.treasury.gov/api-documentation/

Why Ichor cares :
  - bid_to_cover_ratio < 2.0 = weak demand (potential duration shock)
  - high yield drift up = funding-cost pressure
  - "Auction tail" = high_yield - when_issued. when_issued isn't in
    this dataset, so we proxy with high_yield - median_yield.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

import httpx

TREASURY_BASE = "https://api.fiscaldata.treasury.gov/services/api/fiscal_service"
AUCTIONS_ENDPOINT = "/v1/accounting/od/securities_auctions"


@dataclass(frozen=True)
class AuctionResult:
    """One Treasury auction settlement."""

    record_date: date
    issue_date: date
    security_type: str
    security_term: str
    high_yield: float | None
    median_yield: float | None
    low_yield: float | None
    bid_to_cover_ratio: float | None
    fetched_at: datetime

    @property
    def tail_bps(self) -> float | None:
        """Approximate auction tail = (high - median) × 10000.

        The proper tail is (high - when_issued) but when_issued isn't
        published in this dataset. high - median is a reasonable proxy
        — strong auctions tend to clear close to median, weak ones
        leave a gap as the highest accepted bid stretches above.
        """
        if self.high_yield is None or self.median_yield is None:
            return None
        return float(self.high_yield - self.median_yield) * 100.0


def _parse_date(s: Any) -> date | None:
    if s in (None, "", "null"):
        return None
    try:
        return datetime.strptime(str(s)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _parse_float(s: Any) -> float | None:
    if s in (None, "", "null"):
        return None
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def parse_auctions_response(body: dict[str, Any]) -> list[AuctionResult]:
    """fiscaldata returns {data: [...], meta: {...}}."""
    out: list[AuctionResult] = []
    rows = body.get("data") if isinstance(body, dict) else None
    if not isinstance(rows, list):
        return out
    now = datetime.now(UTC)
    for r in rows:
        if not isinstance(r, dict):
            continue
        record_date = _parse_date(r.get("record_date"))
        issue_date = _parse_date(r.get("issue_date"))
        if record_date is None or issue_date is None:
            continue
        out.append(
            AuctionResult(
                record_date=record_date,
                issue_date=issue_date,
                security_type=str(r.get("security_type") or "").strip(),
                security_term=str(r.get("security_term") or "").strip(),
                high_yield=_parse_float(r.get("high_yield")),
                median_yield=_parse_float(r.get("median_yield")),
                low_yield=_parse_float(r.get("low_yield")),
                bid_to_cover_ratio=_parse_float(r.get("bid_to_cover_ratio")),
                fetched_at=now,
            )
        )
    return out


async def fetch_recent_auctions(
    *,
    days: int = 14,
    timeout_s: float = 30.0,
) -> list[AuctionResult]:
    """Pull marketable Treasury auctions from the last `days` days."""
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    url = f"{TREASURY_BASE}{AUCTIONS_ENDPOINT}"
    params = {
        "fields": (
            "record_date,issue_date,security_type,security_term,"
            "high_yield,median_yield,low_yield,bid_to_cover_ratio"
        ),
        "filter": f"issue_date:gte:{cutoff}",
        "sort": "-issue_date",
        "page[size]": "200",
    }
    headers = {
        "Accept": "application/json",
        "User-Agent": "IchorTreasuryAuctionCollector/0.1",
    }
    try:
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            r = await client.get(url, params=params, headers=headers)
            r.raise_for_status()
            return parse_auctions_response(r.json())
    except httpx.HTTPError:
        return []


def supported_security_types() -> tuple[str, ...]:
    """Marketable Treasury security types we surface as alerts."""
    return ("Bill", "Note", "Bond", "FRN", "TIPS", "CMB")
