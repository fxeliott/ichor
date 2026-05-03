"""Pure tests for the narrative tracker tokenizer + report shapes."""

from __future__ import annotations

from ichor_api.services.narrative_tracker import (
    NarrativeReport,
    Topic,
    _tokenize,
    render_narrative_block,
)


def test_tokenize_drops_short_tokens() -> None:
    out = _tokenize("Fed hiked rates by 25bp")
    # "Fed" is 3 chars (drop), "by" stop, "rates" finance-stop,
    # "hiked" 5 chars + not stopword → keep ; "25bp" doesn't match TOKEN_RE
    assert "hiked" in out
    assert "fed" not in out
    assert "by" not in out


def test_tokenize_drops_stopwords() -> None:
    out = _tokenize("The Fed has decided to hold for now")
    for s in ("the", "for", "now"):
        assert s not in out


def test_tokenize_drops_finance_noise() -> None:
    out = _tokenize("Stocks moved higher in trading session")
    for s in ("stocks", "trading", "session", "market"):
        assert s not in out


def test_tokenize_keeps_substantive_keywords() -> None:
    out = _tokenize("Powell hawkish on inflation outlook recession risk")
    assert "powell" in out
    assert "hawkish" in out
    assert "inflation" in out
    assert "recession" in out
    # "outlook" is in finance stopwords
    assert "outlook" not in out


def test_tokenize_handles_empty() -> None:
    assert _tokenize("") == []
    assert _tokenize("   ") == []


def test_tokenize_lowercases() -> None:
    out = _tokenize("POWELL Hawkish")
    assert "powell" in out
    assert "hawkish" in out


def test_render_block_empty_report() -> None:
    report = NarrativeReport(
        window_hours=48, n_documents=0, n_tokens=0, topics=[]
    )
    md, sources = render_narrative_block(report)
    assert "no documents" in md.lower()
    assert sources == []


def test_render_block_with_topics() -> None:
    report = NarrativeReport(
        window_hours=24,
        n_documents=10,
        n_tokens=200,
        topics=[
            Topic(keyword="powell", count=7, share=0.7, sample_titles=("Powell hawkish",)),
            Topic(keyword="inflation", count=5, share=0.5),
        ],
    )
    md, sources = render_narrative_block(report)
    assert "powell" in md.lower()
    assert "inflation" in md.lower()
    assert "70.0%" in md
    assert "Powell hawkish" in md
    assert sources == ["narrative:24h:powell", "narrative:24h:inflation"]


def test_render_block_includes_window_hours() -> None:
    report = NarrativeReport(window_hours=72, n_documents=0, n_tokens=0, topics=[])
    md, _ = render_narrative_block(report)
    assert "72h" in md
