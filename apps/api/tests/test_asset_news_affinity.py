"""Unit tests for `services/asset_news_affinity` (r138 SSOT extract).

The module hosts the keyword-affinity logic that lit-up the news +
geopolitics endpoints (`/v1/news?asset=`, `/v1/geopolitics/briefing?asset=`)
in r138. It was extracted from `services/data_pool._NEWS_KEYWORDS` +
`_matches_asset` (data_pool.py:4519-4552 in r137) under doctrine #4
anti-accumulation SSOT.

These tests pin :
  - the exact keyword set (catches accidental drift in the affinity map)
  - `matches_asset` case-insensitivity + url-fallback semantics
  - `filter_rows_by_asset_affinity` scarce-fallback rule
  - the 5 priority assets (ADR-099 §D-1) all have keywords
  - unknown-asset returns the unfiltered list honestly (no silent drop)
  - back-compat re-imports from `services.data_pool` keep the
    historical private names alive
"""

from __future__ import annotations

import pytest
from ichor_api.services.asset_news_affinity import (
    NEWS_KEYWORDS,
    filter_rows_by_asset_affinity,
    matches_asset,
)

# ─── Keyword map shape pinning ────────────────────────────────────────────


_PRIORITY_5 = ("EUR_USD", "GBP_USD", "XAU_USD", "SPX500_USD", "NAS100_USD")


def test_news_keywords_map_includes_all_5_priority_assets():
    """ADR-099 §D-1 — the 5 surfaced briefing assets must have keywords
    or the asset-conditioned filter falls back to global on each (which
    nullifies the r138 value-add)."""
    for asset in _PRIORITY_5:
        assert asset in NEWS_KEYWORDS, f"missing keywords for {asset}"
        assert len(NEWS_KEYWORDS[asset]) >= 3, f"too few keywords for {asset}"


def test_news_keywords_known_legacy_assets():
    """Round 1 audit: 4 legacy assets (USD_JPY, AUD_USD, USD_CAD, US30_USD)
    still active in the autonomous batch ADR-083 D1 universe — their
    keywords must be preserved across the r138 SSOT migration."""
    for asset in ("USD_JPY", "AUD_USD", "USD_CAD", "US30_USD"):
        assert asset in NEWS_KEYWORDS, f"legacy asset {asset} lost keywords post-r138"


# ─── matches_asset semantics ──────────────────────────────────────────────


def test_matches_asset_case_insensitive_title_hit():
    assert matches_asset("Lagarde ECB speech today", "https://x/y", "EUR_USD")
    assert matches_asset("BUNDESBANK comment on Bund", "https://x/y", "EUR_USD") is False
    # Bundesbank is NOT in the EUR_USD keyword tuple (deliberately — the
    # ECB/Lagarde/eurozone family is the canonical EUR axis).
    assert matches_asset("Powell hawkish Fed funds", "https://x/y", "SPX500_USD")


def test_matches_asset_url_fallback_hit():
    """Keyword should also match if it appears in the URL (some collectors
    don't pull rich titles)."""
    assert matches_asset("", "https://feeds.x.com/EURUSD/2026/05/21", "EUR_USD")
    assert matches_asset("Generic title", "https://x/y/QQQ-flash-crash", "NAS100_USD")


def test_matches_asset_unknown_asset_keeps_all():
    """Honest fallback : unknown asset → return True (caller keeps row)."""
    assert matches_asset("anything", "https://x/y", "ZZZ_UNKNOWN")


def test_matches_asset_no_match():
    assert matches_asset("totally unrelated topic", "https://x/y", "EUR_USD") is False
    assert matches_asset("US politics news", "https://x/y", "XAU_USD") is False


# ─── filter_rows_by_asset_affinity semantics ──────────────────────────────


class _Row:
    """Minimal stand-in for a DB row — anything with title/url works."""

    def __init__(self, title: str, url: str = ""):
        self.title = title
        self.url = url


def _key(r):
    return (r.title, r.url)


def test_filter_applied_when_enough_matches():
    rows = [
        _Row("ECB hikes rates"),
        _Row("Lagarde at IMF"),
        _Row("eurozone PMI weak"),
        _Row("Apple earnings beat"),  # NAS100 territory
    ]
    out, matched, applied = filter_rows_by_asset_affinity(rows, "EUR_USD", _key)
    assert applied is True
    assert matched == 3
    assert len(out) == 3
    assert all("ECB" in r.title or "Lagarde" in r.title or "eurozone" in r.title for r in out)


def test_filter_scarce_fallback_returns_global():
    rows = [
        _Row("ECB hikes rates"),
        _Row("Apple earnings beat"),  # 1 hit only
        _Row("US tariff news"),
    ]
    out, matched, applied = filter_rows_by_asset_affinity(rows, "EUR_USD", _key)
    assert applied is False, "scarce-fallback should fire below min_required"
    assert matched == 1
    assert len(out) == 3, "fallback returns the FULL input list, not the matched subset"


def test_filter_no_asset_returns_unchanged():
    rows = [_Row("x"), _Row("y"), _Row("z")]
    out, matched, applied = filter_rows_by_asset_affinity(rows, None, _key)
    assert applied is False
    assert matched == 0
    assert len(out) == 3


def test_filter_unknown_asset_returns_unchanged():
    """Honest no-silent-drop : unknown asset = no filter attempt, no
    misleading 'matched=N' count."""
    rows = [_Row("x"), _Row("y")]
    out, matched, applied = filter_rows_by_asset_affinity(rows, "FAKE_USD", _key)
    assert applied is False
    assert matched == 0
    assert len(out) == 2


def test_filter_zero_matches_triggers_fallback():
    """0 matches < 3 → scarce-fallback (global feed). Important : the
    panel honest disclosure must say 'aucun item spécifique' in this
    case, not 'filtré' with empty result."""
    rows = [_Row("US tariff debate"), _Row("Fed funds repricing"), _Row("Treasury auction")]
    out, matched, applied = filter_rows_by_asset_affinity(rows, "EUR_USD", _key)
    assert applied is False
    assert matched == 0
    assert len(out) == 3


def test_filter_custom_min_required():
    rows = [_Row("ECB"), _Row("Lagarde")]
    # min_required=2 ⇒ applied at exactly the threshold
    out, matched, applied = filter_rows_by_asset_affinity(rows, "EUR_USD", _key, min_required=2)
    assert applied is True
    assert matched == 2
    assert len(out) == 2


# ─── back-compat with data_pool internal names (lesson #4 SSOT) ──────────


def test_data_pool_back_compat_reexport_present():
    """data_pool.py was re-pointed to import these as `_NEWS_KEYWORDS`
    + `_matches_asset`. Any future module that historically imported
    them from data_pool must still see them."""
    from ichor_api.services.data_pool import _NEWS_KEYWORDS as dp_keys
    from ichor_api.services.data_pool import _matches_asset as dp_matches

    assert dp_keys is NEWS_KEYWORDS, "data_pool re-export must be the same object"
    assert dp_matches is matches_asset, "data_pool re-export must be the same function"


# ─── ADR-017 invariant : keyword vocabulary is content-neutral ───────────


def test_news_keywords_carry_no_directional_words():
    """ADR-017 boundary — keywords describe asset context (tickers,
    central bank names, broad-market terms). They must NOT include
    directional verbs (buy/sell/bullish/bearish/short/long) that would
    leak signal direction through the filter mechanism."""
    forbidden = {"buy", "sell", "long", "short", "bullish", "bearish", "trade"}
    for asset, kws in NEWS_KEYWORDS.items():
        for kw in kws:
            assert kw.lower().strip() not in forbidden, (
                f"ADR-017 leak: directional keyword {kw!r} in {asset}"
            )


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
