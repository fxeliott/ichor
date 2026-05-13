"""Phase D W115c — pocket_skill_reader unit tests.

Pure-Python hysteresis-classifier tests + addendum-render tests +
mocked AsyncSession tests for `read_pocket` happy / flag-off /
pocket-missing / small-sample paths.

Contracts pinned :
* ADR-088 round-28 hysteresis dead-band (2-pp width, enter at ±0.05,
  exit at ±0.03).
* Feature-flag fail-closed (returns None on disabled / absent flag).
* Small-sample shielding (n < 5 always → "neutral" regardless of band).
* ADR-017 boundary intact in `render_pass3_addendum` output (no
  BUY/SELL/TARGET/ENTRY tokens emitted).
"""

from __future__ import annotations

import re
from unittest.mock import AsyncMock, MagicMock

import pytest
from ichor_api.services.pocket_skill_reader import (
    _ANTI_ENTER,
    _ANTI_EXIT,
    _FEATURE_FLAG_NAME,
    _HIGH_ENTER,
    _HIGH_EXIT,
    PocketSkill,
    _classify_band,
    read_pocket,
    render_pass3_addendum,
)

# ─────────────── Hysteresis dead-band constants ────────────────


def test_hysteresis_constants_have_correct_dead_band_width() -> None:
    """ADR-088 round-28 amendment : dead-band width = 2 percentage
    points (0.02) between enter and exit on each side. Trader-review
    YELLOW LOW anti-flicker fix."""
    assert _HIGH_ENTER == 0.05
    assert _HIGH_EXIT == 0.03
    assert _ANTI_ENTER == -0.05
    assert _ANTI_EXIT == -0.03
    assert abs(_HIGH_ENTER - _HIGH_EXIT - 0.02) < 1e-12
    assert abs(_ANTI_ENTER - _ANTI_EXIT + 0.02) < 1e-12


def test_feature_flag_name_matches_adr_088() -> None:
    """ADR-088 § Invariant 2 : flag key string is pinned by the ADR."""
    assert _FEATURE_FLAG_NAME == "phase_d_w115c_confluence_enabled"


# ─────────────── _classify_band (cold-start strict thresholds) ────────


def test_classify_cold_start_high_skill_strict() -> None:
    """Cold-start = previous_band is None → strict enter thresholds.
    skill_delta = +0.05 (exactly the enter threshold) → high_skill."""
    band = _classify_band(0.05, n_observations=10, min_n=5, previous_band=None)
    assert band == "high_skill"


def test_classify_cold_start_just_below_enter_is_neutral() -> None:
    """Cold-start with skill_delta = +0.049 (just below enter) → neutral.
    Verifies the strict `>=` semantics of cold-start."""
    band = _classify_band(0.049, n_observations=10, min_n=5, previous_band=None)
    assert band == "neutral"


def test_classify_cold_start_anti_skill_strict() -> None:
    """Cold-start with skill_delta = -0.05 → anti_skill."""
    band = _classify_band(-0.05, n_observations=10, min_n=5, previous_band=None)
    assert band == "anti_skill"


def test_classify_cold_start_neutral_zone() -> None:
    """Cold-start with skill_delta within (-0.05, +0.05) exclusive → neutral."""
    for delta in (-0.049, -0.01, 0.0, 0.01, 0.049):
        band = _classify_band(delta, n_observations=10, min_n=5, previous_band=None)
        assert band == "neutral", f"skill_delta={delta} should be neutral cold-start"


# ─────────────── _classify_band (hysteresis hold) ────────


def test_classify_hysteresis_holds_high_skill_in_dead_band() -> None:
    """Already in high_skill, skill_delta drops to +0.04 (inside the
    dead-band 0.03..0.05). Should STAY high_skill (no flicker)."""
    band = _classify_band(0.04, n_observations=12, min_n=5, previous_band="high_skill")
    assert band == "high_skill"


def test_classify_hysteresis_holds_anti_skill_in_dead_band() -> None:
    """Already in anti_skill, skill_delta rises to -0.04 (inside
    dead-band -0.05..-0.03). Should STAY anti_skill."""
    band = _classify_band(-0.04, n_observations=13, min_n=5, previous_band="anti_skill")
    assert band == "anti_skill"


def test_classify_hysteresis_exits_high_skill_below_exit_threshold() -> None:
    """Already in high_skill, skill_delta drops to +0.029 (below exit
    threshold +0.03). Should transition to neutral."""
    band = _classify_band(0.029, n_observations=12, min_n=5, previous_band="high_skill")
    assert band == "neutral"


def test_classify_hysteresis_exits_anti_skill_above_exit_threshold() -> None:
    """Already in anti_skill, skill_delta rises to -0.029 (above exit
    threshold -0.03). Should transition to neutral."""
    band = _classify_band(-0.029, n_observations=13, min_n=5, previous_band="anti_skill")
    assert band == "neutral"


# ─────────────── _classify_band (small-sample shielding) ────────


def test_classify_small_sample_always_neutral_high_skill_signal() -> None:
    """n < min_n → neutral regardless of skill_delta. Even a clear
    high_skill signal at +0.20 is silenced when n=4 < min_n=5."""
    band = _classify_band(0.20, n_observations=4, min_n=5, previous_band=None)
    assert band == "neutral"


def test_classify_small_sample_overrides_previous_anti_skill() -> None:
    """Small-sample shielding overrides hysteresis : even if previously
    anti_skill, n=2 < min_n=5 forces neutral. Prevents stale
    classifications from leaking through degraded pockets."""
    band = _classify_band(-0.20, n_observations=2, min_n=5, previous_band="anti_skill")
    assert band == "neutral"


def test_classify_at_min_n_threshold_unblocks() -> None:
    """n == min_n is the unblocking boundary : at n=5 with min_n=5,
    classification proceeds normally."""
    band = _classify_band(-0.06, n_observations=5, min_n=5, previous_band=None)
    assert band == "anti_skill"


# ─────────────── render_pass3_addendum ADR-017 boundary ────────


_FORBIDDEN_TOKENS_RE = re.compile(
    r"\b(BUY|SELL|LONG\s+NOW|SHORT\s+NOW|TP\d*|SL\d*|TARGET[\s:]+\d+|"
    r"ENTRY[\s:]+\d+|MARGIN\s+CALL|take[\s_-]*profit|stop[\s_-]*loss)\b",
    re.IGNORECASE,
)


def _make_skill(band: str, delta: float = 0.0, n: int = 10) -> PocketSkill:
    return PocketSkill(
        asset="EUR_USD",
        regime="usd_complacency",
        pocket_version=1,
        prod_weight=0.30,
        climatology_weight=0.35,
        equal_weight_weight=0.35,
        skill_delta=delta,
        n_observations=n,
        confidence_band=band,  # type: ignore[arg-type]
    )


@pytest.mark.parametrize("band", ["high_skill", "neutral", "anti_skill"])
def test_render_addendum_never_emits_adr017_forbidden_tokens(band: str) -> None:
    """ADR-017 boundary : the addendum text MUST NOT contain BUY/SELL/
    TP/SL/TARGET/ENTRY/MARGIN CALL tokens regardless of band classification."""
    skill = _make_skill(band, delta=-0.05 if band == "anti_skill" else 0.06)
    text = render_pass3_addendum(skill)
    matches = _FORBIDDEN_TOKENS_RE.findall(text)
    assert matches == [], f"Addendum for {band} leaked tokens : {matches}\nText : {text!r}"


def test_render_addendum_includes_asset_regime_and_metrics() -> None:
    """Addendum must mention asset, regime, n_observations, and skill_delta
    for traceability. Source-stamping discipline."""
    skill = _make_skill("anti_skill", delta=-0.0497, n=13)
    text = render_pass3_addendum(skill)
    assert "EUR_USD" in text
    assert "usd_complacency" in text
    assert "n=13" in text
    assert "-0.0497" in text


def test_render_addendum_distinguishes_three_bands() -> None:
    """Each band must produce visibly distinct framing language so
    Pass-3 stress can adjust its invalidation discipline."""
    high = render_pass3_addendum(_make_skill("high_skill", delta=0.10))
    neutral = render_pass3_addendum(_make_skill("neutral", delta=0.01))
    anti = render_pass3_addendum(_make_skill("anti_skill", delta=-0.10))
    assert "more reliable" in high
    assert "less reliable" in anti
    assert "marginal" in neutral
    # Sanity : the three texts are distinct.
    assert high != neutral
    assert neutral != anti
    assert high != anti


# ─────────────── read_pocket (mocked AsyncSession) ────────


@pytest.mark.asyncio
async def test_read_pocket_returns_none_when_feature_flag_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ADR-088 § Invariant 2 : flag OFF → None (fail-closed). Zero SQL
    queries should fire if flag is off."""
    session = MagicMock()
    session.execute = AsyncMock()

    async def _flag_disabled(_sess, _key) -> bool:  # noqa: ANN001
        return False

    monkeypatch.setattr("ichor_api.services.pocket_skill_reader.is_enabled", _flag_disabled)

    result = await read_pocket(session, asset="EUR_USD", regime="usd_complacency")
    assert result is None
    session.execute.assert_not_called()  # short-circuit before any SQL


@pytest.mark.asyncio
async def test_read_pocket_returns_none_on_incomplete_pocket(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A pocket missing one of the 3 expert kinds (prod_predictor /
    climatology / equal_weight) is treated as 'no data' → None.
    Defensive : should never happen if Vovk cron is correct."""
    session = MagicMock()
    # Mock scalars().all() to return only 2 of 3 experts.
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [
        MagicMock(expert_kind="prod_predictor", weight=0.30, n_observations=10),
        MagicMock(expert_kind="climatology", weight=0.35, n_observations=10),
        # missing equal_weight !
    ]
    session.execute = AsyncMock(return_value=mock_result)

    async def _flag_enabled(_sess, _key) -> bool:  # noqa: ANN001
        return True

    monkeypatch.setattr("ichor_api.services.pocket_skill_reader.is_enabled", _flag_enabled)

    result = await read_pocket(session, asset="EUR_USD", regime="usd_complacency")
    assert result is None


@pytest.mark.asyncio
async def test_read_pocket_happy_path_returns_pocket_skill(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Happy path : flag ON + 3 expert rows + n >= min_n → returns
    PocketSkill with the right skill_delta + confidence_band."""
    session = MagicMock()
    mock_result = MagicMock()
    # NB float precision : `0.30 - 0.35` evaluates to -0.04999999999999998
    # which is GREATER than -0.05 → would return neutral. Use 0.29 / 0.35
    # → skill_delta = -0.06 (clearly below the _ANTI_ENTER threshold).
    # Production realised weights are persisted as DB Float so this float
    # subtraction reflects real conditions ; the test pins the
    # unambiguous-below-threshold case.
    mock_result.scalars.return_value.all.return_value = [
        MagicMock(expert_kind="prod_predictor", weight=0.29, n_observations=13),
        MagicMock(expert_kind="climatology", weight=0.35, n_observations=13),
        MagicMock(expert_kind="equal_weight", weight=0.35, n_observations=13),
    ]
    session.execute = AsyncMock(return_value=mock_result)

    async def _flag_enabled(_sess, _key) -> bool:  # noqa: ANN001
        return True

    monkeypatch.setattr("ichor_api.services.pocket_skill_reader.is_enabled", _flag_enabled)

    result = await read_pocket(session, asset="EUR_USD", regime="usd_complacency")
    assert result is not None
    assert result.asset == "EUR_USD"
    assert result.regime == "usd_complacency"
    assert result.pocket_version == 1
    assert abs(result.skill_delta - (-0.06)) < 1e-9
    assert result.n_observations == 13
    # Cold-start (previous_band=None default) : skill_delta = -0.06
    # clearly below _ANTI_ENTER threshold (-0.05) → anti_skill.
    assert result.confidence_band == "anti_skill"


@pytest.mark.asyncio
async def test_read_pocket_small_sample_returns_neutral(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """n < min_n_observations → returns PocketSkill but with
    confidence_band=neutral (small-sample shielding). The skill_delta
    is still computed so callers can inspect, but the band is forced."""
    session = MagicMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [
        MagicMock(expert_kind="prod_predictor", weight=0.20, n_observations=3),
        MagicMock(expert_kind="climatology", weight=0.40, n_observations=3),
        MagicMock(expert_kind="equal_weight", weight=0.40, n_observations=3),
    ]
    session.execute = AsyncMock(return_value=mock_result)

    async def _flag_enabled(_sess, _key) -> bool:  # noqa: ANN001
        return True

    monkeypatch.setattr("ichor_api.services.pocket_skill_reader.is_enabled", _flag_enabled)

    result = await read_pocket(session, asset="GBP_USD", regime="usd_complacency")
    assert result is not None
    # skill_delta = -0.20 would be clear anti_skill, but n=3 < min=5 → neutral
    assert abs(result.skill_delta - (-0.20)) < 1e-12
    assert result.confidence_band == "neutral"
    assert result.n_observations == 3
