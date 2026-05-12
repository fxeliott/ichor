"""Unit tests for `services.rag_embeddings` — ADR-086 doctrinal invariants."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from ichor_api.services.rag_embeddings import (
    EMBEDDING_DIM,
    EMBEDDING_MODEL_NAME,
    Analogue,
    _format_vector_for_pgvector,
    format_analogues_prompt_section,
    retrieve_analogues,
)


@pytest.mark.asyncio
async def test_retrieve_analogues_rejects_zero_embargo() -> None:
    """ADR-086 Invariant 1 : embargo_days >= 1 MANDATORY."""
    session = AsyncMock()
    with pytest.raises(ValueError, match="embargo_days must be >= 1"):
        await retrieve_analogues(
            session, query_text="test", query_at=datetime.now(UTC), embargo_days=0
        )


@pytest.mark.asyncio
async def test_retrieve_analogues_rejects_negative_embargo() -> None:
    session = AsyncMock()
    with pytest.raises(ValueError, match="embargo_days must be >= 1"):
        await retrieve_analogues(
            session, query_text="test", query_at=datetime.now(UTC), embargo_days=-1
        )


@pytest.mark.asyncio
async def test_retrieve_analogues_rejects_invalid_k() -> None:
    session = AsyncMock()
    with pytest.raises(ValueError, match=r"k must be in"):
        await retrieve_analogues(session, query_text="test", query_at=datetime.now(UTC), k=0)
    with pytest.raises(ValueError, match=r"k must be in"):
        await retrieve_analogues(session, query_text="test", query_at=datetime.now(UTC), k=51)


def test_format_vector_for_pgvector_round_trip() -> None:
    vec = [0.1, -0.5, 1.234567890]
    literal = _format_vector_for_pgvector(vec)
    assert literal.startswith("[")
    assert literal.endswith("]")
    parts = literal.strip("[]").split(",")
    assert len(parts) == 3
    assert abs(float(parts[0]) - 0.1) < 1e-7
    assert abs(float(parts[2]) - 1.234567890) < 1e-7


def test_format_vector_empty_list() -> None:
    assert _format_vector_for_pgvector([]) == "[]"


def test_format_analogues_prompt_section_empty() -> None:
    assert format_analogues_prompt_section([]) == ""


def test_format_analogues_prompt_section_renders_basic() -> None:
    analogue = Analogue(
        chunk_id="abc",
        source_type="session_card",
        source_id="xyz",
        asset="EUR_USD",
        regime="goldilocks",
        section=None,
        content="Régime usd_complacency 72% confidence...",
        created_at=datetime(2024, 11, 8, tzinfo=UTC),
        cosine_distance=0.123,
    )
    out = format_analogues_prompt_section([analogue])
    assert "## Historical analogues" in out
    assert "2024-11-08" in out
    assert "asset=EUR_USD" in out
    assert "regime=goldilocks" in out
    assert "cos_dist=0.123" in out
    assert "Régime usd_complacency" in out
    assert "ADR-017 boundary" in out


def test_format_analogues_truncates_long_content() -> None:
    long_content = "x" * 1000
    analogue = Analogue(
        chunk_id="a",
        source_type="session_card",
        source_id="b",
        asset="EUR_USD",
        regime=None,
        section=None,
        content=long_content,
        created_at=datetime(2024, 1, 1, tzinfo=UTC),
        cosine_distance=0.5,
    )
    out = format_analogues_prompt_section([analogue])
    assert "…" in out
    assert "x" * 500 not in out


def test_embedding_model_constants() -> None:
    """ADR-086 Invariant 2 pins the model name + dimension."""
    assert EMBEDDING_MODEL_NAME == "BAAI/bge-small-en-v1.5"
    assert EMBEDDING_DIM == 384


@pytest.mark.asyncio
async def test_retrieve_analogues_calls_session_execute_with_past_only_filter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Confirms WHERE clause includes `created_at < :cutoff`."""
    from ichor_api.services import rag_embeddings

    monkeypatch.setattr(rag_embeddings, "embed_text", lambda _t: [0.0] * 384)

    captured: dict = {}

    async def fake_execute(sql, params):  # noqa: ANN001
        captured["sql"] = str(sql)
        captured["params"] = params
        m = MagicMock()
        m.mappings.return_value.all.return_value = []
        return m

    session = AsyncMock()
    session.execute = fake_execute
    now = datetime(2024, 11, 8, 12, 0, 0, tzinfo=UTC)

    await retrieve_analogues(session, query_text="test", query_at=now, asset="EUR_USD", k=5)

    assert "created_at < :cutoff" in captured["sql"]
    assert "embedding <=> CAST(:qv AS vector)" in captured["sql"]
    assert captured["params"]["cutoff"] < now
    assert captured["params"]["k"] == 5
    assert captured["params"]["asset"] == "EUR_USD"
