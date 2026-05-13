"""Unit tests for collectors/ecb_estr.py (round-34, ADR-090 step-4).

Verifies the €STR collector :
  1. parse_estr_csv handles ECB Data Portal SDMX-CSV 1.0.0 with
     **COMMA delimiter** (NOT semicolon like Bundesbank — per-provider
     variant, anti-bug-class-recurrence vs r32c).
  2. parse_estr_xml handles SDMX-ML fallback shape correctly.
  3. parse_estr_response auto-detects via content-type header AND via
     body-start sniffing.
  4. Empty cells (non-trading days) are skipped silently.
  5. Malformed rows are skipped, not raised.
  6. UTF-8 BOM is handled (utf-8-sig decode).
  7. fetch_estr_rates returns [] on HTTP error (graceful).
  8. URL has NO `?format=csvdata` (r32c lesson — Bundesbank rejects it).
"""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from ichor_api.collectors.ecb_estr import (
    ECB_ESTR_URL_BASE,
    EstrObservation,
    fetch_estr_rates,
    parse_estr_csv,
    parse_estr_response,
    parse_estr_xml,
)

# ──────────────────────── parse_estr_csv ────────────────────────


def test_csv_parses_canonical_ecb_shape() -> None:
    """ECB Data Portal SDMX-CSV 1.0.0 with COMMA delimiter."""
    csv_text = (
        "KEY,FREQ,REF_AREA,SUBJECT,TIME_PERIOD,OBS_VALUE,OBS_STATUS,CONF_STATUS\n"
        "EST.B.EU000A2X2A25.WT,B,EU000A2X2A25,WT,2026-05-12,1.929,A,F\n"
        "EST.B.EU000A2X2A25.WT,B,EU000A2X2A25,WT,2026-05-09,1.931,A,F\n"
    )
    out = parse_estr_csv(csv_text)
    assert len(out) == 2
    assert out[0].observation_date == date(2026, 5, 12)
    assert out[0].rate_pct == 1.929
    assert out[1].observation_date == date(2026, 5, 9)
    assert out[1].rate_pct == 1.931


def test_csv_skips_empty_value_rows() -> None:
    """Non-trading days have empty OBS_VALUE — must be silently skipped."""
    csv_text = (
        "KEY,FREQ,REF_AREA,SUBJECT,TIME_PERIOD,OBS_VALUE\n"
        "EST,B,EU,WT,2026-05-12,1.929\n"
        "EST,B,EU,WT,2026-05-10,\n"
        "EST,B,EU,WT,2026-05-09,1.931\n"
    )
    out = parse_estr_csv(csv_text)
    assert len(out) == 2
    assert out[0].observation_date == date(2026, 5, 12)
    assert out[1].observation_date == date(2026, 5, 9)


def test_csv_skips_malformed_rows() -> None:
    """Bad date / non-numeric value rows : skip, don't raise."""
    csv_text = (
        "TIME_PERIOD,OBS_VALUE\n"
        "2026-05-12,1.929\n"
        "not-a-date,2.0\n"
        "2026-05-10,not-a-number\n"
        "2026-05-09,1.931\n"
    )
    out = parse_estr_csv(csv_text)
    assert len(out) == 2
    assert {o.observation_date for o in out} == {date(2026, 5, 12), date(2026, 5, 9)}


def test_csv_handles_utf8_bom() -> None:
    """ECB sometimes returns content with BOM — strip cleanly."""
    csv_text = "﻿TIME_PERIOD,OBS_VALUE\n2026-05-12,1.929\n"
    out = parse_estr_csv(csv_text)
    assert len(out) == 1
    assert out[0].observation_date == date(2026, 5, 12)


# ──────────────────────── parse_estr_xml ────────────────────────


def test_xml_parses_sdmx_generic_data() -> None:
    """SDMX-ML 2.1 generic data shape — used if Accept negotiates XML."""
    xml_text = """<?xml version="1.0" ?>
<message:GenericData xmlns:message="http://www.sdmx.org/resources/sdmxml/schemas/v2_1/message"
                     xmlns:generic="http://www.sdmx.org/resources/sdmxml/schemas/v2_1/data/generic">
  <message:DataSet>
    <generic:Series>
      <generic:Obs>
        <generic:ObsDimension value="2026-05-12"/>
        <generic:ObsValue value="1.929"/>
      </generic:Obs>
      <generic:Obs>
        <generic:ObsDimension value="2026-05-09"/>
        <generic:ObsValue value="1.931"/>
      </generic:Obs>
    </generic:Series>
  </message:DataSet>
</message:GenericData>
"""
    out = parse_estr_xml(xml_text)
    assert len(out) == 2
    assert out[0].observation_date == date(2026, 5, 12)
    assert out[0].rate_pct == 1.929


def test_xml_returns_empty_on_parse_error() -> None:
    """Malformed XML : log warning + return [], don't raise."""
    out = parse_estr_xml("<not-valid-xml-at-all")
    assert out == []


# ──────────────────────── parse_estr_response auto-detect ────────────────────────


def test_response_auto_detects_csv_via_content_type() -> None:
    csv_bytes = b"TIME_PERIOD,OBS_VALUE\n2026-05-12,1.929\n"
    out = parse_estr_response(csv_bytes, content_type="application/vnd.sdmx.data+csv;version=1.0.0")
    assert len(out) == 1


def test_response_auto_detects_xml_via_content_type() -> None:
    xml_bytes = b"""<?xml version="1.0"?>
<message:GenericData xmlns:message="http://www.sdmx.org/resources/sdmxml/schemas/v2_1/message"
                     xmlns:generic="http://www.sdmx.org/resources/sdmxml/schemas/v2_1/data/generic">
  <message:DataSet>
    <generic:Series>
      <generic:Obs>
        <generic:ObsDimension value="2026-05-12"/>
        <generic:ObsValue value="1.929"/>
      </generic:Obs>
    </generic:Series>
  </message:DataSet>
</message:GenericData>
"""
    out = parse_estr_response(xml_bytes, content_type="application/xml")
    assert len(out) == 1


def test_response_auto_detects_xml_via_body_start() -> None:
    """Even when content-type is generic, body starting with '<' → XML path."""
    xml_text = """<?xml version="1.0"?>
<message:GenericData xmlns:message="http://www.sdmx.org/resources/sdmxml/schemas/v2_1/message"
                     xmlns:generic="http://www.sdmx.org/resources/sdmxml/schemas/v2_1/data/generic">
  <message:DataSet>
    <generic:Series>
      <generic:Obs>
        <generic:ObsDimension value="2026-05-12"/>
        <generic:ObsValue value="1.929"/>
      </generic:Obs>
    </generic:Series>
  </message:DataSet>
</message:GenericData>
"""
    out = parse_estr_response(xml_text, content_type="application/octet-stream")
    assert len(out) == 1


# ──────────────────────── fetch_estr_rates (HTTP error path) ────────────────────────


@pytest.mark.asyncio
async def test_fetch_returns_empty_on_http_error() -> None:
    """Network blip / 5xx / timeout → graceful empty return."""
    fake_client = AsyncMock()
    fake_client.get = AsyncMock(side_effect=httpx.RequestError("simulated"))
    out = await fetch_estr_rates(client=fake_client)
    assert out == []


@pytest.mark.asyncio
async def test_fetch_passes_start_period_to_url() -> None:
    """`start_period` kwarg appends `?startPeriod=YYYY-MM-DD` to URL."""
    response_mock = MagicMock()
    response_mock.raise_for_status = MagicMock()
    response_mock.headers = {"content-type": "application/vnd.sdmx.data+csv;version=1.0.0"}
    response_mock.content = b"TIME_PERIOD,OBS_VALUE\n2026-05-12,1.929\n"
    fake_client = AsyncMock()
    fake_client.get = AsyncMock(return_value=response_mock)
    out = await fetch_estr_rates(client=fake_client, start_period=date(2026, 5, 1))
    assert len(out) == 1
    # Verify the URL passed to client.get includes the startPeriod query.
    call_args = fake_client.get.await_args
    url_arg = call_args.args[0]
    assert "startPeriod=2026-05-01" in url_arg


# ──────────────────────── anti-bug-class regressions ────────────────────────


def test_url_base_does_not_include_format_param() -> None:
    """r32c lesson : Bundesbank rejected ?format=csvdata with HTTP 406.
    ECB also doesn't need the format query — Accept header drives the
    content negotiation. Pin the URL base WITHOUT ?format=."""
    assert "?format=" not in ECB_ESTR_URL_BASE
    assert ECB_ESTR_URL_BASE.endswith("WT")


def test_csv_parser_uses_comma_delimiter_not_semicolon() -> None:
    """r32c carry-forward : Bundesbank uses ; but ECB uses , — these
    are PER-PROVIDER. Catch a regression that copy-pastes ; into the
    €STR collector by feeding semicolon-CSV and verifying it returns []."""
    semicolon_text = "TIME_PERIOD;OBS_VALUE\n2026-05-12;1.929\n"
    out = parse_estr_csv(semicolon_text)
    # With comma-delimiter, the semicolon-CSV is parsed as ONE column,
    # row.get("TIME_PERIOD") → None, value_str empty, row skipped.
    assert out == []


# ──────────────────────── EstrObservation dataclass ────────────────────────


def test_observation_is_frozen() -> None:
    """Defense-in-depth : freeze the dataclass so accidental mutation
    in downstream code is caught at runtime."""
    obs = EstrObservation(
        observation_date=date(2026, 5, 12),
        rate_pct=1.929,
        source_url="https://...",
        fetched_at=__import__("datetime").datetime(2026, 5, 12, tzinfo=__import__("datetime").UTC),
    )
    with pytest.raises(Exception):  # FrozenInstanceError or AttributeError
        obs.rate_pct = 2.0  # type: ignore[misc]
