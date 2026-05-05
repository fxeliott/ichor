"""Tests for the Wave 3.3+3.4 post_mortem additions.

Asserts :
  - `_build_suggestions` flags asset miss clusters (>= 3 in top-5)
  - It surfaces drift-flagged assets
  - It calls `meta_prompt_tuner.detect_rollback` per (pass, scope)
  - It returns a clean "info" entry when nothing fires
  - The rendered markdown shows the new richer drift section
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from ichor_api.services.post_mortem import (
    PostMortemPayload,
    _build_suggestions,
    render_markdown,
)


class _StubSession:
    """Minimal AsyncSession placeholder ; suggestion builder doesn't query
    the DB itself — it delegates to mocked `detect_rollback`."""


@pytest.mark.asyncio
async def test_clean_week_emits_info_only() -> None:
    session = _StubSession()
    with patch(
        "ichor_api.services.meta_prompt_tuner.detect_rollback",
        new=AsyncMock(return_value=(False, "Brier delta 0.0001 within tolerance")),
    ):
        out = await _build_suggestions(session, top_miss=[], drift_detected=[])  # type: ignore[arg-type]
    assert len(out) == 1
    assert out[0]["kind"] == "info"
    assert "no actionable amendments" in out[0]["title"].lower()


@pytest.mark.asyncio
async def test_asset_miss_cluster_3_or_more_flags_reweight() -> None:
    session = _StubSession()
    top_miss: list[dict[str, Any]] = [
        {"asset": "EUR_USD", "brier_contribution": 0.62},
        {"asset": "EUR_USD", "brier_contribution": 0.55},
        {"asset": "EUR_USD", "brier_contribution": 0.48},
        {"asset": "GBP_USD", "brier_contribution": 0.42},
        {"asset": "USD_JPY", "brier_contribution": 0.38},
    ]
    with patch(
        "ichor_api.services.meta_prompt_tuner.detect_rollback",
        new=AsyncMock(return_value=(False, "ok")),
    ):
        out = await _build_suggestions(session, top_miss=top_miss, drift_detected=[])  # type: ignore[arg-type]
    reweight = [s for s in out if s["kind"] == "reweight"]
    assert len(reweight) == 1
    assert "EUR_USD" in reweight[0]["title"]


@pytest.mark.asyncio
async def test_asset_cluster_below_3_does_not_flag() -> None:
    session = _StubSession()
    top_miss = [
        {"asset": "EUR_USD"},
        {"asset": "EUR_USD"},
        {"asset": "GBP_USD"},
    ]
    with patch(
        "ichor_api.services.meta_prompt_tuner.detect_rollback",
        new=AsyncMock(return_value=(False, "ok")),
    ):
        out = await _build_suggestions(session, top_miss=top_miss, drift_detected=[])  # type: ignore[arg-type]
    assert not any(s["kind"] == "reweight" for s in out)


@pytest.mark.asyncio
async def test_drift_flagged_assets_surface() -> None:
    session = _StubSession()
    drift = [
        {
            "asset": "USD_JPY",
            "drift_at_index": 122,
            "n_residuals": 130,
            "last_brier": 0.55,
            "mean_brier_window": 0.45,
        }
    ]
    with patch(
        "ichor_api.services.meta_prompt_tuner.detect_rollback",
        new=AsyncMock(return_value=(False, "ok")),
    ):
        out = await _build_suggestions(session, top_miss=[], drift_detected=drift)  # type: ignore[arg-type]
    drift_entries = [s for s in out if s["kind"] == "drift"]
    assert len(drift_entries) == 1
    assert "USD_JPY" in drift_entries[0]["title"]


@pytest.mark.asyncio
async def test_drift_capped_at_3_most_degraded() -> None:
    session = _StubSession()
    drift = [
        {
            "asset": f"PAIR_{i}",
            "drift_at_index": 100,
            "n_residuals": 110,
            "last_brier": 0.5,
            "mean_brier_window": 0.4,
        }
        for i in range(5)
    ]
    with patch(
        "ichor_api.services.meta_prompt_tuner.detect_rollback",
        new=AsyncMock(return_value=(False, "ok")),
    ):
        out = await _build_suggestions(session, top_miss=[], drift_detected=drift)  # type: ignore[arg-type]
    drift_entries = [s for s in out if s["kind"] == "drift"]
    assert len(drift_entries) == 3


@pytest.mark.asyncio
async def test_rollback_fires_for_each_pass_scope_when_degraded() -> None:
    session = _StubSession()

    # detect_rollback returns True for Pass 1 only, False for the rest
    async def _mock_rollback(_session: Any, *, pass_index: int, scope: str) -> tuple[bool, str]:
        if pass_index == 1 and scope == "regime":
            return (True, "Brier degraded by 0.0150 on 7d window")
        return (False, "ok")

    with patch("ichor_api.services.meta_prompt_tuner.detect_rollback", new=_mock_rollback):
        out = await _build_suggestions(session, top_miss=[], drift_detected=[])  # type: ignore[arg-type]
    rollbacks = [s for s in out if s["kind"] == "rollback"]
    assert len(rollbacks) == 1
    assert "Pass 1" in rollbacks[0]["title"]
    assert "regime" in rollbacks[0]["title"]


@pytest.mark.asyncio
async def test_rollback_handler_swallows_exceptions() -> None:
    session = _StubSession()

    async def _boom(_session: Any, *, pass_index: int, scope: str) -> tuple[bool, str]:
        raise RuntimeError("DB unavailable")

    with patch("ichor_api.services.meta_prompt_tuner.detect_rollback", new=_boom):
        # Should NOT raise, falls back to clean info
        out = await _build_suggestions(session, top_miss=[], drift_detected=[])  # type: ignore[arg-type]
    assert len(out) == 1
    assert out[0]["kind"] == "info"


@pytest.mark.asyncio
async def test_combined_signals_emit_multiple_suggestions() -> None:
    session = _StubSession()
    top_miss = [{"asset": "XAU_USD"} for _ in range(4)]
    drift = [
        {
            "asset": "EUR_USD",
            "drift_at_index": 50,
            "n_residuals": 60,
            "last_brier": 0.55,
            "mean_brier_window": 0.42,
        }
    ]

    async def _mock_rollback(_session: Any, *, pass_index: int, scope: str) -> tuple[bool, str]:
        return (pass_index == 2, "Brier delta 0.020")

    with patch("ichor_api.services.meta_prompt_tuner.detect_rollback", new=_mock_rollback):
        out = await _build_suggestions(
            session,
            top_miss=top_miss,
            drift_detected=drift,  # type: ignore[arg-type]
        )
    kinds = {s["kind"] for s in out}
    assert "reweight" in kinds
    assert "drift" in kinds
    assert "rollback" in kinds


# ─────────────────── render_markdown — drift section ───────────────────


def _payload(drift: list[dict[str, Any]], suggestions: list[dict[str, Any]]) -> PostMortemPayload:
    from datetime import UTC, datetime

    return PostMortemPayload(
        iso_year=2026,
        iso_week=18,
        generated_at=datetime(2026, 5, 4, 18, 0, tzinfo=UTC),
        top_hits=[],
        top_miss=[],
        drift_detected=drift,
        narratives=[],
        calibration={"brier_7d": None, "brier_30d": None, "brier_90d": None},
        suggestions=suggestions,
        stats={"n_top_hits": 0, "n_top_miss": 0, "n_narratives": 0},
    )


def test_render_drift_section_shows_richer_format() -> None:
    drift = [
        {
            "asset": "USD_JPY",
            "drift_at_index": 122,
            "n_residuals": 130,
            "last_brier": 0.55,
            "mean_brier_window": 0.452,
        }
    ]
    md = render_markdown(_payload(drift, []))
    assert "## 4. Drift detected" in md
    assert "USD_JPY" in md
    assert "0.452" in md
    assert "122/130" in md


def test_render_drift_section_clean_when_empty() -> None:
    md = render_markdown(_payload([], []))
    assert "## 4. Drift detected" in md
    assert "(no drift flags in this window)" in md


def test_render_suggestions_uses_kind_emojis() -> None:
    sugg = [
        {"kind": "reweight", "title": "Re-weight EUR_USD", "rationale": "3 misses"},
        {"kind": "drift", "title": "Drift on USD_JPY", "rationale": "0.45 mean Brier"},
        {"kind": "rollback", "title": "Rollback Pass 1", "rationale": "+0.015"},
    ]
    md = render_markdown(_payload([], sugg))
    assert "⚖️" in md
    assert "📉" in md
    assert "↩️" in md
