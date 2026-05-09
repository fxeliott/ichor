"""MyFXBook Community Outlook collector — retail FX positioning ratios.

The MyFXBook Community Outlook is a real-time aggregate of long/short
positioning across MyFXBook's connected retail trader population. Used
by Ichor as a contrarian sentiment indicator: extreme retail positioning
(>75 % long or short) often precedes a reversal — retail crowd is
typically late-cycle.

Why this matters for Ichor :
- Replaces the discontinued OANDA Open Position Ratios endpoint
  (sunset by OANDA Sept 2024; their replacement Data Service costs
  $1850/mo on 12-month contract — incompatible with Voie D ADR-009).
- MyFXBook free tier: 100 req/24h hard limit, IP-bound session.
- Pairs of interest: EUR/USD, GBP/USD, USD/JPY, AUD/USD, USD/CAD,
  XAU/USD (the 6 Ichor monitors).

Free path verified Voie D-compliant (ADR-009): MyFXBook free API,
session token via email/password (no OAuth, no metered billing).
License: "any software developed using the API should be free" —
research-internal use OK with attribution.

Self-selection bias: sample = traders who voluntarily linked their
account. Not representative of all retail. Documented in CbAssetImpact
narratives surfaced by data_pool.

DORMANT BY DEFAULT: this collector silently skips when env vars
ICHOR_API_MYFXBOOK_EMAIL or ICHOR_API_MYFXBOOK_PASSWORD are missing.
Eliot must signup at myfxbook.com (free) and set the two env vars in
/etc/ichor/api.env to activate.

Strategy :
  1. Read email + password from settings (return [] silently if missing).
  2. POST /api/login.json → session_id.
  3. GET /api/get-community-outlook.json?session=<id> → symbols[].
  4. Filter for the 6 Ichor pairs.
  5. Persist one row per pair per fetch (no dedup — historical view).
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from datetime import UTC, datetime

import httpx
import structlog

log = structlog.get_logger(__name__)

LOGIN_URL = "https://www.myfxbook.com/api/login.json"
OUTLOOK_URL = "https://www.myfxbook.com/api/get-community-outlook.json"

ICHOR_PAIRS: frozenset[str] = frozenset(
    {"EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "XAUUSD"}
)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; IchorCollector/1.0; +https://github.com/fxeliott/ichor)"
    ),
    "Accept": "application/json,*/*",
}


@dataclass(frozen=True)
class MyfxbookOutlookSnapshot:
    """One MyFXBook Community Outlook snapshot per pair."""

    pair: str
    long_pct: float
    short_pct: float
    long_volume: float | None
    short_volume: float | None
    avg_long_price: float | None
    avg_short_price: float | None
    long_positions: int | None
    short_positions: int | None
    fetched_at: datetime


def _read_credentials() -> tuple[str, str] | None:
    """Read MyFXBook email + password from env. Returns None if missing."""
    email = os.environ.get("ICHOR_API_MYFXBOOK_EMAIL", "").strip()
    pwd = os.environ.get("ICHOR_API_MYFXBOOK_PASSWORD", "").strip()
    if not email or not pwd:
        return None
    return email, pwd


async def login(client: httpx.AsyncClient, email: str, password: str) -> str | None:
    """POST /api/login.json → session_id. Returns None on failure."""
    try:
        # MyFXBook v1 API uses query params for login, not POST body.
        r = await client.get(
            LOGIN_URL,
            params={"email": email, "password": password},
            timeout=30.0,
        )
        r.raise_for_status()
        data = r.json()
    except (httpx.HTTPError, ValueError) as e:
        log.warning("myfxbook.login_failed", error=str(e))
        return None
    if not isinstance(data, dict) or data.get("error", True):
        log.warning(
            "myfxbook.login_rejected",
            message=str(data.get("message", "")) if isinstance(data, dict) else "",
        )
        return None
    session_id = data.get("session")
    return session_id if isinstance(session_id, str) and session_id else None


def _to_float(v: object) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)  # type: ignore[arg-type]
    except (ValueError, TypeError):
        return None


def _to_int(v: object) -> int | None:
    if v is None or v == "":
        return None
    try:
        return int(v)  # type: ignore[arg-type]
    except (ValueError, TypeError):
        return None


def parse_outlook_payload(payload: dict, fetched_at: datetime) -> list[MyfxbookOutlookSnapshot]:
    """Pure parser — extract Ichor pairs from MyFXBook outlook JSON.

    Schema sample (per MyFXBook docs):
        {"error": false, "symbols": [
            {"name": "EURUSD",
             "shortPercentage": 65.0, "longPercentage": 35.0,
             "shortVolume": 1234.5, "longVolume": 567.8,
             "longPositions": 1234, "shortPositions": 5678,
             "avgShortPrice": 1.0850, "avgLongPrice": 1.0820},
            ...
        ]}
    """
    if not isinstance(payload, dict):
        return []
    if payload.get("error", True):
        return []
    symbols = payload.get("symbols") or []
    if not isinstance(symbols, list):
        return []
    out: list[MyfxbookOutlookSnapshot] = []
    for sym in symbols:
        if not isinstance(sym, dict):
            continue
        pair = str(sym.get("name") or "").upper().replace("/", "")
        if pair not in ICHOR_PAIRS:
            continue
        long_pct = _to_float(sym.get("longPercentage"))
        short_pct = _to_float(sym.get("shortPercentage"))
        if long_pct is None or short_pct is None:
            continue
        out.append(
            MyfxbookOutlookSnapshot(
                pair=pair,
                long_pct=long_pct,
                short_pct=short_pct,
                long_volume=_to_float(sym.get("longVolume")),
                short_volume=_to_float(sym.get("shortVolume")),
                avg_long_price=_to_float(sym.get("avgLongPrice")),
                avg_short_price=_to_float(sym.get("avgShortPrice")),
                long_positions=_to_int(sym.get("longPositions")),
                short_positions=_to_int(sym.get("shortPositions")),
                fetched_at=fetched_at,
            )
        )
    return out


async def fetch_outlook(
    client: httpx.AsyncClient, session_id: str
) -> list[MyfxbookOutlookSnapshot]:
    """GET /api/get-community-outlook.json → list[MyfxbookOutlookSnapshot]."""
    try:
        r = await client.get(
            OUTLOOK_URL,
            params={"session": session_id},
            timeout=30.0,
        )
        r.raise_for_status()
        data = r.json()
    except (httpx.HTTPError, ValueError) as e:
        log.warning("myfxbook.outlook_failed", error=str(e))
        return []
    return parse_outlook_payload(data, datetime.now(UTC))


async def poll_all() -> list[MyfxbookOutlookSnapshot]:
    """Standard collector entry point. Silent skip if creds missing."""
    creds = _read_credentials()
    if creds is None:
        log.info("myfxbook.dormant", reason="ICHOR_API_MYFXBOOK_EMAIL/PASSWORD unset")
        return []
    email, password = creds
    async with httpx.AsyncClient(timeout=30.0, headers=_HEADERS) as client:
        session_id = await login(client, email, password)
        if session_id is None:
            return []
        return await fetch_outlook(client, session_id)


__all__ = [
    "ICHOR_PAIRS",
    "LOGIN_URL",
    "OUTLOOK_URL",
    "MyfxbookOutlookSnapshot",
    "fetch_outlook",
    "login",
    "parse_outlook_payload",
    "poll_all",
]


if __name__ == "__main__":  # pragma: no cover
    rows = asyncio.run(poll_all())
    print(f"fetched {len(rows)} outlook rows")
    for r in rows:
        print(
            f"  {r.pair}  long={r.long_pct:.1f}%  short={r.short_pct:.1f}%  "
            f"vol_l={r.long_volume}  vol_s={r.short_volume}"
        )
