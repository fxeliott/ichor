"""ADR-090 P0 step-1 — Bundesbank Bund 10Y collector parser tests.

Pure-Python parser tests against synthetic SDMX-CSV + SDMX-ML fixtures
that mirror the empirically-observed Bundesbank response shape (round
28 researcher blueprint validated 2026-05-13 = 3.13% PROZENT).

No live HTTP fetch — `fetch_bund_yields` is exercised via httpx
MockTransport in a separate integration test (not shipped this round).
"""

from __future__ import annotations

from datetime import date

import pytest
from ichor_api.collectors.bundesbank_bund import (
    BUND_10Y_URL,
    BundYieldObservation,
    parse_bund_csv,
    parse_bund_response,
    parse_bund_xml,
)

# ─────────────── SDMX-CSV fixtures ────────────────

# NOTE round-37 (2026-05-14) : Bundesbank SDMX-CSV uses SEMICOLON `;`
# delimiter (per SDMX 2.1 spec `vnd.sdmx.data+csv;version=1.0.0` and
# round-32c 2026-05-13 empirical production response). Fixtures below
# mirror the actual production shape — using a comma here would NOT
# match what the parser is calibrated against and would silently
# return 0 rows (the bug class round-37 r32c-followup closes).
_CSV_HAPPY = """\
KEY;TIME_PERIOD;OBS_VALUE;UNIT;FREQUENCY
BBSIS.D.I.ZAR.ZI.EUR.S1311.B.A604.R10XX.R.A.A._Z._Z.A;2026-05-11;3.10;PROZENT;D
BBSIS.D.I.ZAR.ZI.EUR.S1311.B.A604.R10XX.R.A.A._Z._Z.A;2026-05-12;3.12;PROZENT;D
BBSIS.D.I.ZAR.ZI.EUR.S1311.B.A604.R10XX.R.A.A._Z._Z.A;2026-05-13;3.13;PROZENT;D
"""

_CSV_WITH_EMPTY_CELLS = """\
KEY;TIME_PERIOD;OBS_VALUE;UNIT;FREQUENCY
BBSIS.X;2026-05-11;3.10;PROZENT;D
BBSIS.X;2026-05-12;;PROZENT;D
BBSIS.X;2026-05-13;3.13;PROZENT;D
"""

_CSV_WITH_GARBAGE_ROW = """\
KEY;TIME_PERIOD;OBS_VALUE;UNIT;FREQUENCY
BBSIS.X;2026-05-11;3.10;PROZENT;D
BBSIS.X;not-a-date;7.77;PROZENT;D
BBSIS.X;2026-05-13;not-a-number;PROZENT;D
BBSIS.X;2026-05-14;3.14;PROZENT;D
"""

# ─────────────── SDMX-ML fixtures ────────────────

_XML_HAPPY = """\
<?xml version="1.0" encoding="UTF-8"?>
<DataSet xmlns:generic="http://www.sdmx.org/resources/sdmxml/schemas/v2_1/data/generic">
  <generic:Series>
    <generic:Obs>
      <generic:ObsDimension value="2026-05-11"/>
      <generic:ObsValue value="3.10"/>
    </generic:Obs>
    <generic:Obs>
      <generic:ObsDimension value="2026-05-12"/>
      <generic:ObsValue value="3.12"/>
    </generic:Obs>
    <generic:Obs>
      <generic:ObsDimension value="2026-05-13"/>
      <generic:ObsValue value="3.13"/>
    </generic:Obs>
  </generic:Series>
</DataSet>
"""

_XML_MALFORMED = "this is not xml at all"


# ─────────────── parse_bund_csv ────────────────


def test_parse_csv_happy_path_three_rows() -> None:
    """SDMX-CSV with 3 valid rows → 3 BundYieldObservation."""
    out = parse_bund_csv(_CSV_HAPPY)
    assert len(out) == 3
    dates = [o.observation_date for o in out]
    yields = [o.yield_pct for o in out]
    assert dates == [date(2026, 5, 11), date(2026, 5, 12), date(2026, 5, 13)]
    assert yields == [3.10, 3.12, 3.13]
    # All rows should carry the canonical source URL.
    for o in out:
        assert o.source_url == BUND_10Y_URL


def test_parse_csv_skips_empty_obs_value() -> None:
    """Non-trading days have empty OBS_VALUE — skipped without raising."""
    out = parse_bund_csv(_CSV_WITH_EMPTY_CELLS)
    assert len(out) == 2
    assert all(o.yield_pct > 0 for o in out)


def test_parse_csv_skips_malformed_rows() -> None:
    """Garbage date or garbage value → row skipped, NOT exception."""
    out = parse_bund_csv(_CSV_WITH_GARBAGE_ROW)
    # Keep only 2026-05-11 (3.10) and 2026-05-14 (3.14) ; skip both
    # malformed rows.
    assert len(out) == 2
    dates = sorted(o.observation_date for o in out)
    assert dates == [date(2026, 5, 11), date(2026, 5, 14)]


def test_parse_csv_empty_body_returns_empty() -> None:
    """Empty body / header-only → []."""
    assert parse_bund_csv("") == []
    assert parse_bund_csv("KEY,TIME_PERIOD,OBS_VALUE\n") == []


# ─────────────── parse_bund_xml ────────────────


def test_parse_xml_happy_path_three_rows() -> None:
    """SDMX-ML with 3 <generic:Obs> → 3 BundYieldObservation."""
    out = parse_bund_xml(_XML_HAPPY)
    assert len(out) == 3
    dates = sorted(o.observation_date for o in out)
    yields = sorted(o.yield_pct for o in out)
    assert dates == [date(2026, 5, 11), date(2026, 5, 12), date(2026, 5, 13)]
    assert yields == [3.10, 3.12, 3.13]


def test_parse_xml_malformed_returns_empty() -> None:
    """Non-XML body → [] (not exception). Defensive : caller logs the
    fetch_failed path, not the parser."""
    assert parse_bund_xml(_XML_MALFORMED) == []


def test_parse_xml_empty_document_returns_empty() -> None:
    """Valid XML but zero <Obs> elements → []."""
    empty_doc = '<?xml version="1.0"?><DataSet/>'
    assert parse_bund_xml(empty_doc) == []


# ─────────────── parse_bund_response (auto-detect) ────────────────


def test_response_dispatches_to_csv_when_content_type_csv() -> None:
    """Explicit `content_type: text/csv` → CSV parser."""
    out = parse_bund_response(_CSV_HAPPY, content_type="text/csv")
    assert len(out) == 3


def test_response_dispatches_to_xml_when_content_type_xml() -> None:
    """Explicit `content_type: application/xml` → XML parser."""
    out = parse_bund_response(_XML_HAPPY, content_type="application/xml")
    assert len(out) == 3


def test_response_detects_xml_from_body_prefix() -> None:
    """Body starts with `<?xml` → XML parser, no content_type needed."""
    out = parse_bund_response(_XML_HAPPY, content_type="")
    assert len(out) == 3


def test_response_falls_back_to_xml_when_csv_yields_zero() -> None:
    """Default CSV-first dispatch falls back to XML when CSV parses 0
    rows. Defensive : Bundesbank server has been observed to ignore
    `?format=csvdata` and return XML anyway (researcher round 28
    finding)."""
    # XML body but no content_type header — should still parse.
    body = _XML_HAPPY.lstrip()  # strip leading newline so it starts with `<?xml`
    out = parse_bund_response(body)
    assert len(out) == 3


def test_response_handles_bytes_input() -> None:
    """The httpx response body is bytes ; decoder must handle UTF-8 BOM."""
    body_bytes = ("﻿" + _CSV_HAPPY).encode("utf-8")
    out = parse_bund_response(body_bytes, content_type="text/csv")
    assert len(out) == 3


# ─────────────── BundYieldObservation ────────────────


def test_observation_dataclass_is_frozen() -> None:
    """`@dataclass(frozen=True)` — caller cannot mutate after parsing."""
    obs = BundYieldObservation(
        observation_date=date(2026, 5, 13),
        yield_pct=3.13,
        source_url=BUND_10Y_URL,
        fetched_at=date(2026, 5, 13),  # type: ignore[arg-type]  # runtime check
    )
    with pytest.raises(Exception):
        obs.yield_pct = 4.0  # type: ignore[misc]  # mutation must raise
