"""ECB SDMX collector — eurozone macro series via the ECB Data Portal.

Replaces the gap left by FRED for ECB-specific data (HICP, eurozone PMI,
TLTRO, M3, eurozone HY OAS Bloomberg-mirrored). Free, no API key.

Endpoint:
  https://data-api.ecb.europa.eu/service/data/{flow}/{key}?format=jsondata&lastNObservations=N

The ECB SDMX 2.1 API is verbose; this collector reduces it to a flat list.

Series Ichor cares about:
  - ICP.M.U2.N.000000.4.ANR        HICP eurozone YoY
  - BSI.M.U2.Y.V.M30.X.1.U2.2300.Z01.E   M3 eurozone YoY
  - DD.M.U2.4F_M.MAINREFI.LEVEL    Main refinancing rate (MRO)
  - QSA.Q.N.I8.W0.S1.S1.B.B6N.Z._Z._Z._Z.EUR.S.V.A1   GDP nominal eurozone
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import httpx

ECB_BASE = "https://data-api.ecb.europa.eu/service/data"

SERIES_TO_POLL: tuple[tuple[str, str], ...] = (
    ("ICP", "M.U2.N.000000.4.ANR"),  # HICP YoY
    ("BSI", "M.U2.Y.V.M30.X.1.U2.2300.Z01.E"),  # M3 YoY
    ("DD", "M.U2.4F_M.MAINREFI.LEVEL"),  # MRO rate
)


@dataclass(frozen=True)
class EcbObservation:
    """One ECB SDMX observation reduced to a flat row."""

    flow: str  # e.g. "ICP"
    series_key: str  # e.g. "M.U2.N.000000.4.ANR"
    observation_period: str  # ISO month/quarter (e.g. "2026-04")
    value: float | None
    fetched_at: datetime


def parse_ecb_response(body: dict, flow: str, series_key: str) -> list[EcbObservation]:
    """SDMX 2.1 is layered; we only need the (period, value) pairs.

    Structure:
      body['dataSets'][0]['series'][SERIES_KEY]['observations'][PERIOD_INDEX]
        = [value, observation_attrs...]
      body['structure']['dimensions']['observation'][0]['values'][PERIOD_INDEX]
        = {'id': '2026-04', 'name': '2026-04'}
    """
    fetched = datetime.now(UTC)
    datasets = body.get("dataSets") or []
    if not datasets:
        return []
    series_dict = datasets[0].get("series") or {}
    if not series_dict:
        return []
    # Use the first (and only) series block
    series_block = next(iter(series_dict.values()))
    obs = series_block.get("observations") or {}

    structure = body.get("structure") or {}
    obs_dims = (structure.get("dimensions") or {}).get("observation") or []
    period_values: list[dict] = []
    if obs_dims:
        period_values = obs_dims[0].get("values") or []

    out: list[EcbObservation] = []
    for idx_str, payload in obs.items():
        try:
            idx = int(idx_str)
        except (TypeError, ValueError):
            continue
        period = ""
        if 0 <= idx < len(period_values):
            period = str(period_values[idx].get("id") or "")
        if not isinstance(payload, list) or not payload:
            continue
        v: float | None
        try:
            v = float(payload[0]) if payload[0] is not None else None
        except (TypeError, ValueError):
            v = None
        out.append(
            EcbObservation(
                flow=flow,
                series_key=series_key,
                observation_period=period,
                value=v,
                fetched_at=fetched,
            )
        )
    out.sort(key=lambda x: x.observation_period, reverse=True)
    return out


async def fetch_series(
    flow: str,
    series_key: str,
    *,
    last_n: int = 36,
    timeout_s: float = 20.0,
) -> list[EcbObservation]:
    """Latest N observations for one series."""
    headers = {"Accept": "application/json"}
    url = f"{ECB_BASE}/{flow}/{series_key}"
    params = {"format": "jsondata", "lastNObservations": str(last_n)}
    try:
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            r = await client.get(url, params=params, headers=headers)
            r.raise_for_status()
            return parse_ecb_response(r.json(), flow, series_key)
    except httpx.HTTPError:
        return []
