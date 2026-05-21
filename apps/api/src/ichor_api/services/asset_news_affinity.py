"""Asset news/geopolitics keyword affinity — single source of truth.

Extracted r138 (ADR-099 §Impl, doctrine #4 anti-accumulation SSOT) from
`services/data_pool.py` where `_NEWS_KEYWORDS` + `_matches_asset` had
lived since r68. The 4-pass LLM data-pool was the only consumer ; the
public `/v1/news` and `/v1/geopolitics/briefing` endpoints ignored the
`?asset=` query param and served a global feed identical for all 5
priority assets (R59-AUDIT 2026-05-21 empirical, Stream α).

Moving the constants + helpers here gives :
  - `data_pool.py` keeps semantic-identical behaviour (re-export).
  - `routers/news.py` can filter by asset.
  - `routers/geopolitics.py` can filter GDELT events by asset.

Public surface (used by all 3 consumers — keep stable) :
  - `NEWS_KEYWORDS`              : `dict[str, tuple[str, ...]]`
  - `matches_asset(title, url, asset)` : bool
  - `filter_rows_by_asset_affinity(rows, asset, key, min_required=3)` :
      generic helper. `rows` = arbitrary objects. `key` returns the
      blob to match against. Returns `(filtered_rows, applied: bool)`
      where `applied=False` means the asset filter was attempted but
      yielded fewer than `min_required` matches → fell back to the
      original list (caller surfaces the honest fallback flag).

ADR-017 boundary : keywords describe ASSET CONTEXT (tickers, central
bank names, broad-market terms) and are CONTENT-NEUTRAL — they do not
encode direction (no "bullish gold" / "bearish euro" patterns). The
filter narrows news/events to the asset's CONVERSATION, never biases.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable

# r138 — SSOT for the asset query-param regex shared by `/v1/news` and
# `/v1/geopolitics/briefing` (code-reviewer N3 r138 — prevents drift
# between the two routers' duplicate definitions of the same shape).
ASSET_QUERY_REGEX = r"^[A-Z0-9_]{3,16}$"

# r68 origin (data_pool.py:4519-4542). r138 re-homed here unchanged.
# 5 priority assets per ADR-099 §D-1 PLUS the historical 4 (USD_JPY /
# AUD_USD / USD_CAD / US30_USD) kept so the 4-pass autonomous batch
# (which still polls these as ADR-083 D1 universe) keeps its filter.
NEWS_KEYWORDS: dict[str, tuple[str, ...]] = {
    "EUR_USD": ("EUR/USD", "EURUSD", "EUR ", "euro", "ECB", "Lagarde", "eurozone"),
    "GBP_USD": ("GBP/USD", "GBPUSD", "GBP ", "pound sterling", "BoE", "Bailey", "UK economy"),
    "USD_JPY": ("USD/JPY", "USDJPY", "JPY ", "yen", "BoJ", "Ueda", "Japan inflation"),
    "AUD_USD": ("AUD/USD", "AUDUSD", "AUD ", "Aussie", "RBA", "iron ore", "Australia"),
    "USD_CAD": ("USD/CAD", "USDCAD", "CAD ", "loonie", "BoC", "Macklem", "Canadian"),
    "XAU_USD": ("XAU/USD", "XAUUSD", "gold", "bullion", "GLD ", "GDX ", "spot metals"),
    "NAS100_USD": (
        "NAS100",
        "Nasdaq",
        "NASDAQ",
        "QQQ",
        "AAPL",
        "MSFT",
        "GOOGL",
        "AMZN",
        "META",
        "NVDA",
        "TSLA",
        "tech stocks",
    ),
    "SPX500_USD": ("S&P 500", "SPX", "SPY", "S&P500", "broad market", "Fed funds"),
    "US30_USD": ("Dow Jones", "DJIA", "DIA"),
}


def matches_asset(title: str, url: str, asset: str) -> bool:
    """Heuristic ticker-link: case-insensitive keyword match in title OR
    URL path. Returns True if no keywords are configured for the asset
    (unknown → keep all, honest fallback)."""
    keys = NEWS_KEYWORDS.get(asset.upper())
    if not keys:
        return True
    blob = f"{title} {url}".lower()
    return any(k.lower() in blob for k in keys)


def filter_rows_by_asset_affinity[T](
    rows: Iterable[T],
    asset: str | None,
    key: Callable[[T], tuple[str, str]],
    *,
    min_required: int = 3,
) -> tuple[list[T], int, bool]:
    """Filter `rows` by asset-keyword affinity with a scarce-fallback.

    Args:
      rows: arbitrary iterable of items (DB rows, dicts, etc.).
      asset: asset code (e.g. "EUR_USD") or None to skip filtering.
      key: returns `(title, url)` strings to match against the asset's
           keyword tuple.
      min_required: minimum matched items to keep the filter applied.
                    Below this threshold we fall back to the original
                    unfiltered list (honest: small-N filter would be
                    noisier than the global feed).

    Returns:
      `(returned_rows, matched_count, applied)` where :
        - returned_rows: the filtered list if `applied=True`,
                        else the original list (scarce fallback).
        - matched_count: how many items matched the asset's keywords
                         pre-fallback (so callers can surface the
                         honest "X items match {asset}" disclosure).
        - applied: True iff the filter narrowed the result set.

    When `asset is None` returns `(list(rows), 0, False)` — the caller
    sees `applied=False` and renders the global flow.
    """
    rows_list = list(rows)
    if not asset:
        return rows_list, 0, False
    asset_uc = asset.upper()
    if asset_uc not in NEWS_KEYWORDS:
        # Unknown asset: keep all (honest, NO silent drop).
        return rows_list, 0, False
    matched = [r for r in rows_list if matches_asset(*key(r), asset_uc)]
    if len(matched) < min_required:
        # Scarce-fallback: not enough asset-specific items — fall back
        # to global. Caller surfaces this state via `applied=False`.
        return rows_list, len(matched), False
    return matched, len(matched), True
