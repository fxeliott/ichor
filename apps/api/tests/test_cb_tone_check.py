"""Unit tests for services/cb_tone_check.py.

Wires the previously DORMANT FOMC_TONE_SHIFT + ECB_TONE_SHIFT alerts.
The FOMC-Roberta scorer is mocked so tests don't trigger a 1.4 GB
model download.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from ichor_api.services.cb_tone_check import (
    _MIN_HISTORY,
    _zscore,
    evaluate_cb_tone,
)

# ── pure z-score helper ────────────────────────────────────────────


def test_zscore_returns_none_when_short() -> None:
    assert _zscore([0.0] * (_MIN_HISTORY - 1), 0.5) is None


def test_zscore_classic_two_sigma() -> None:
    history = [0.0] * 25 + [1.0] * 25  # mean=0.5, std=0.5
    assert _zscore(history, 1.5) == pytest.approx(2.0, abs=1e-9)


# ── evaluate_cb_tone (mock DB + mock scorer) ───────────────────────


def _mock_speech(text: str) -> MagicMock:
    s = MagicMock()
    s.summary = text
    s.title = ""
    s.published_at = datetime.now(UTC)
    return s


def _build_session(
    *,
    speeches: list[MagicMock],
    history_values: list[float],
    existing_today: bool = False,
    persist: bool = False,
) -> MagicMock:
    """Mock session whose .execute() returns deterministic results
    in the order evaluate_cb_tone makes them.

    With persist=True: speeches → existence-check → read_history.
    With persist=False: speeches → read_history (existence-check
    is skipped because _persist_tone is never called).
    """
    session = MagicMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()

    def _scalars_all_result(values):
        r = MagicMock()
        scalars = MagicMock()
        scalars.all = MagicMock(return_value=values)
        r.scalars = MagicMock(return_value=scalars)
        return r

    def _scalar_result(value):
        r = MagicMock()
        r.scalar_one_or_none = MagicMock(return_value=value)
        return r

    def _all_result(values):
        r = MagicMock()
        r.all = MagicMock(return_value=[(v,) for v in values])
        return r

    queue: list[MagicMock] = [_scalars_all_result(speeches)]
    if persist:
        queue.append(_scalar_result("existing-id" if existing_today else None))
    queue.append(_all_result(history_values))

    async def _execute(*args, **kwargs):
        if queue:
            return queue.pop(0)
        empty = MagicMock()
        empty.scalar_one_or_none = MagicMock(return_value=None)
        empty.all = MagicMock(return_value=[])
        empty.first = MagicMock(return_value=None)
        empty.scalar = MagicMock(return_value=None)
        scalars = MagicMock()
        scalars.all = MagicMock(return_value=[])
        empty.scalars = MagicMock(return_value=scalars)
        return empty

    session.execute = _execute
    return session


@pytest.mark.asyncio
async def test_returns_no_speech_path() -> None:
    session = _build_session(speeches=[], history_values=[])
    result = await evaluate_cb_tone(
        session, cb="FED", scorer=lambda t: 0.0, persist=False
    )
    assert result.n_speeches == 0
    assert result.net_hawkish is None
    assert "no FED speech" in result.note


@pytest.mark.asyncio
async def test_aggregates_net_hawkish_across_speeches() -> None:
    speeches = [_mock_speech("hawkish text"), _mock_speech("dovish text")]
    # Scorer returns +0.6 for first, -0.2 for second → mean +0.2.
    scores = iter([0.6, -0.2])

    def scorer(text: str) -> float:
        return next(scores)

    session = _build_session(speeches=speeches, history_values=[0.0] * 50)
    result = await evaluate_cb_tone(
        session, cb="FED", scorer=scorer, persist=False
    )
    assert result.n_speeches == 2
    assert result.net_hawkish == pytest.approx(0.2, abs=1e-9)


@pytest.mark.asyncio
async def test_z_score_computed_when_history_sufficient() -> None:
    speeches = [_mock_speech("text")]
    # 50-pt history symmetric around 0 → std small. Today's value far
    # from mean → high z.
    history = [0.001] * 25 + [-0.001] * 25
    session = _build_session(speeches=speeches, history_values=history + [0.005])
    result = await evaluate_cb_tone(
        session, cb="FED", scorer=lambda t: 0.005, persist=False
    )
    assert result.z_score is not None
    assert result.z_score > 4.0


@pytest.mark.asyncio
async def test_unmapped_cb_skips_alert_but_still_persists() -> None:
    """A CB code not in CB_TO_METRIC (e.g. 'BOJ') must not crash —
    we persist the tone series + return the result, just don't
    fire the catalog alert."""
    speeches = [_mock_speech("text")]
    session = _build_session(speeches=speeches, history_values=[0.0] * 50)
    # persist=False so we don't actually write
    result = await evaluate_cb_tone(
        session, cb="BOJ", scorer=lambda t: 0.1, persist=False
    )
    assert result.cb == "BOJ"
    assert result.series_id == "BOJ_TONE_NET"
    assert result.net_hawkish == pytest.approx(0.1)


@pytest.mark.asyncio
async def test_speeches_with_no_text_returns_none() -> None:
    s = MagicMock()
    s.summary = ""
    s.title = ""
    session = _build_session(speeches=[s], history_values=[])
    result = await evaluate_cb_tone(
        session, cb="FED", scorer=lambda t: 0.5, persist=False
    )
    assert result.n_speeches == 1
    assert result.net_hawkish is None
    assert "no usable text" in result.note
