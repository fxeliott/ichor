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
# r139 keyword precision pass : empirically-grounded SPX/NAS/XAU expansion
# (7-day Hetzner news_items SQL survey + Phase 1B web research). Every
# new keyword has a non-zero empirical match count on the prod news_items
# table over 7 days (see SESSION_LOG_2026-05-21-r139-EXECUTION.md §A
# for the verbatim count). Candidates with 0 empirical matches and known
# high false-positive surnames (Daly/Logan/Bowman/MOVE) were dropped
# from the add-list per Stream 1B FP flag analysis.
#
# Trailing-space gotcha (r68 + r139 caveat) : "GLD " and "GDX " carry a
# trailing space to prevent substring noise (e.g. "OLD"→"GLD" or
# "XGDP"→"GDX"). Do NOT add new keywords with trailing spaces unless
# they have the same disambiguation need ; modern additions (Nvidia,
# Marvell, Broadcom, etc.) use full names that don't collide.
#
# ADR-017 keyword-content-neutrality CI guard
# (`test_news_keywords_carry_no_directional_words`) enforces zero
# directional verbs (buy/sell/long/short/bullish/bearish/trade). "rate
# cut" / "rate cuts" are kept as EVENT LABELS (not actions) — Stream 1B
# documented edge-case acceptance.
#
# 5 priority assets per ADR-099 §D-1 PLUS the historical 4 (USD_JPY /
# AUD_USD / USD_CAD / US30_USD) kept so the 4-pass autonomous batch
# (which still polls these as ADR-083 D1 universe) keeps its filter.
NEWS_KEYWORDS: dict[str, tuple[str, ...]] = {
    "EUR_USD": ("EUR/USD", "EURUSD", "EUR ", "euro", "ECB", "Lagarde", "eurozone"),
    "GBP_USD": ("GBP/USD", "GBPUSD", "GBP ", "pound sterling", "BoE", "Bailey", "UK economy"),
    "USD_JPY": ("USD/JPY", "USDJPY", "JPY ", "yen", "BoJ", "Ueda", "Japan inflation"),
    "AUD_USD": ("AUD/USD", "AUDUSD", "AUD ", "Aussie", "RBA", "iron ore", "Australia"),
    "USD_CAD": ("USD/CAD", "USDCAD", "CAD ", "loonie", "BoC", "Macklem", "Canadian"),
    "XAU_USD": (
        # r68 existing — kept (gold/bullion/GLD/GDX/XAU ~94 matches/7d on prod)
        "XAU/USD",
        "XAUUSD",
        "gold",
        "bullion",
        "GLD ",  # trailing-space disambiguation vs "OLD"/"BUILD"/etc.
        "GDX ",  # trailing-space disambiguation vs "XGDP"/etc.
        "spot metals",
        # r139 mechanical drivers — empirical-validated (7d Hetzner survey)
        # r139 code-reviewer SF-2 — "real yield" substring catches "real yields"
        # plural redundancy. Dropped "real yields" (same coverage via substring).
        "real yield",  # 11 matches (gold opportunity-cost mechanical channel)
        "10-year Treasury",  # 36 matches (nominal yield input to real-yield calc)
        "de-dollarization",  # 10 matches (structural CB-gold demand driver)
    ),
    "NAS100_USD": (
        # r68 existing — kept (Nasdaq/NASDAQ/QQQ ~275 + mega-caps ~600 matches/7d)
        "NAS100",
        "Nasdaq",
        "NASDAQ",
        "QQQ",
        "AAPL",  # 0 empirical 7d (news uses "Apple"/Tim Cook) — kept for URL paths
        "MSFT",  # 10
        "GOOGL",  # 306
        "AMZN",  # 20
        "META",  # 238
        "NVDA",  # 58 (vs "Nvidia" full-name 974 — see r139 adds)
        "TSLA",  # 0 empirical (news uses "Tesla") — kept for URL paths
        "tech stocks",  # 81 empirical (generic but volume justifies)
        # r139 mega-cap full names + AI capex + semis (empirical 7d Hetzner)
        "Nvidia",  # 974 matches — FULL-NAME catches what NVDA ticker misses
        "data center",  # 250 matches (hyperscaler capex narrative)
        "datacenter",  # 21 matches (one-word variant)
        "GPU",  # 143 matches (NVDA/AMD direct hardware vocab)
        "hyperscaler",  # 133 matches (MSFT/AMZN/GOOGL/META AI capex framing)
        "AMD",  # 82 matches (second-source GPU thesis)
        "Marvell",  # 50 matches (custom silicon)
        "Broadcom",  # 49 matches (Google TPU co-designer)
        "Blackwell",  # 41 matches (NVDA chip codename)
        "Taiwan Semiconductor",  # 39 matches (foundry dependency)
        "TSMC",  # 10 matches (short-form, complementary)
        "Netflix",  # 32 matches (NDX top-10)
        "foundry",  # 30 matches (TSMC/Intel framing)
        "Applied Materials",  # 27 matches (semi equipment)
        "Palantir",  # 20 matches (NDX growth)
        # r139 code-reviewer SF-4 + trader YELLOW-1 — full-name "Tim Cook"
        # has IDENTICAL 9-match title+url coverage to bare "Cook" but ZERO
        # false-positive surface (bare "Cook" could collide with Cook County /
        # Cookson surname / cookies / cooking). Empirically verified via SQL.
        "Tim Cook",  # 9 title+url matches (Apple CEO disambiguated full-name)
        "CHIPS Act",  # 11 matches (tech/policy)
        "AI accelerator",  # 11 matches (chip vocab)
        "LLM",  # 10 matches (AI vocab)
        "SOXX",  # 10 matches (semis ETF)
    ),
    "SPX500_USD": (
        # r68 existing — kept (S&P 500 = 323 matches/7d on prod, dominant baseline)
        "S&P 500",
        "SPX",
        "SPY",  # 10
        "S&P500",
        "Fed funds",  # 0 empirical 7d but well-anchored Fed-policy label — keep
        # r139 — DROPPED "broad market" (0 empirical matches, generic noise)
        # r139 Fed people + macro releases (empirical-validated 7d Hetzner)
        "Warsh",  # 21 matches — NEW Fed chair sworn in 2026-05-16
        "Powell",  # 11 matches (chair pro tempore, governor through 2028)
        "Williams",  # 10 matches (NY Fed Vice Chair FOMC permanent voter)
        "ISM",  # 87 matches (Manufacturing + Services PMI = top SPX catalyst)
        "PMI",  # 11 matches (S&P Global Flash)
        "CPI",  # 10 matches (Fed inflation indicator)
        "PCE",  # 11 matches (Fed's preferred inflation measure)
        # r139 code-reviewer SF-2 — "rate cut" substring matches "rate cuts"
        # plural by the substring matcher's nature. Dropped "rate cuts"
        # explicitly to remove redundant entry (same 21 matches/7d coverage).
        "rate cut",  # 21 matches — event-label, not directional (ADR-017 edge-case)
        "tariff",  # 13 matches (2026 stagflation driver, Trump policy)
        "10-year Treasury",  # 36 matches (discount-rate input, shared with XAU)
    ),
    "US30_USD": ("Dow Jones", "DJIA", "DIA"),
}


def matches_asset(title: str, url: str, asset: str, summary: str = "") -> bool:
    """Heuristic ticker-link: case-insensitive keyword match in title OR
    URL path OR summary. Returns True if no keywords are configured for
    the asset (unknown → keep all, honest fallback).

    r139 — added optional `summary` parameter. The r68 original matched
    title+url only ; the r139 empirical Hetzner survey discovered that
    most macro-vocabulary content (FOMC/PMI/CPI/real-yields/etc.) lives
    in the news_items.summary field, NOT the title. Title+url-only match
    rendered ~70% of the r139 keyword precision additions functionally-
    zero (the keywords were added to NEWS_KEYWORDS but never fired against
    title+url matching). Adding summary as a 3rd blob field surfaces the
    keyword precision pass empirically (lesson #2 SHIPPED ≠ FUNCTIONAL).

    Backward-compat : `summary=""` default preserves the pre-r139 behaviour
    for callers that don't pass a summary."""
    keys = NEWS_KEYWORDS.get(asset.upper())
    if not keys:
        return True
    blob = f"{title} {url} {summary}".lower()
    return any(k.lower() in blob for k in keys)


def filter_rows_by_asset_affinity[T](
    rows: Iterable[T],
    asset: str | None,
    key: Callable[[T], tuple[str, ...]],
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
    # r139 — support both 2-tuple (title, url) and 3-tuple (title, url, summary)
    # `key` callables for backward-compat with r138 callers + the new r139
    # matcher-extension that includes summary. Empirical Hetzner survey 2026-05-22
    # showed ~70% of macro-vocabulary content lives in summary, not title/url.
    matched: list[T] = []
    for r in rows_list:
        fields = key(r)
        title = fields[0] if len(fields) > 0 else ""
        url = fields[1] if len(fields) > 1 else ""
        summary = fields[2] if len(fields) > 2 else ""
        if matches_asset(title, url, asset_uc, summary):
            matched.append(r)
    if len(matched) < min_required:
        # Scarce-fallback: not enough asset-specific items — fall back
        # to global. Caller surfaces this state via `applied=False`.
        return rows_list, len(matched), False
    return matched, len(matched), True
