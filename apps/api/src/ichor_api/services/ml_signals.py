"""ML signals adapter — wires `packages/ml/*` into the data_pool.

Phase 2 fix for SPEC.md §2.2 #12 (ML packages scaffolded but never imported
from apps/api). This module is the single bridge between the implemented
ML modules in `ichor_ml.*` and the brain's data_pool consumed by Pass 1/2.

Design:
  - Each adapter runs the relevant ML compute INLINE (fit-on-the-fly for
    HMM / HAR-RV ; aggregation for FinBERT ; lazy HF load for FOMC-RoBERTa).
  - Heavy/blocking compute is dispatched via `asyncio.to_thread` so the
    event loop is not stalled.
  - Every adapter is wrapped in try/except: if the ML deps are not
    installed (the `[ml]` extra) or the model fails to converge, we fall
    back to an honest `placeholder` row instead of breaking the data_pool.
  - VPIN and SABR-SVI remain honest placeholders: VPIN needs trade-tape
    granularity we don't persist (only 1-min bars), SABR-SVI is explicitly
    deferred (SPEC §2.2 #15).

Status semantics:
  - "ok"          → live ML output (fitted this call OR aggregated cached value).
  - "placeholder" → dependency missing OR insufficient data.
  - "error"       → unexpected exception ; logged.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import (
    CbSpeech,
    FxTick,
    MarketDataBar,
    NewsItem,
    Prediction,
)

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class MlSignal:
    """One ML signal output (or placeholder)."""

    name: str
    value: str
    horizon: str | None = None
    status: str = "ok"


async def _daily_returns(session: AsyncSession, asset: str, *, days: int = 250) -> list[float]:
    """Last N close-to-close simple returns from market_data (Stooq)."""
    cutoff = datetime.now(UTC) - timedelta(days=days * 2)
    rows = list(
        (
            await session.execute(
                select(MarketDataBar)
                .where(MarketDataBar.asset == asset, MarketDataBar.bar_ts >= cutoff)
                .order_by(MarketDataBar.bar_ts.asc())
            )
        )
        .scalars()
        .all()
    )
    closes = [float(r.close) for r in rows if r.close is not None]
    if len(closes) < 2:
        return []
    return [
        (closes[i] - closes[i - 1]) / closes[i - 1]
        for i in range(1, len(closes))
        if closes[i - 1] != 0
    ][-days:]


# ─────────────────────────────────────────────────────────────────────
# HMM régime — fit-on-the-fly on (log_ret, |ret|_5d_avg, |ret|_22d_avg)
# ─────────────────────────────────────────────────────────────────────


def _hmm_compute(returns: list[float]) -> tuple[int, float, bool] | None:
    """Sync compute (called via to_thread). Returns (state, prob, converged) or None."""
    try:
        import numpy as np
        from ichor_ml.regime import HMMRegimeDetector
    except ImportError as exc:
        log.debug("ichor_ml not installed: %s", exc)
        return None

    rets = np.asarray(returns, dtype=np.float64)
    if rets.size < 60:
        return None

    # Build 3-feature matrix [log_ret, abs_ret_5d_avg, abs_ret_22d_avg].
    # Approximation: simple returns ≈ log returns for small daily moves.
    log_ret = rets
    abs_ret = np.abs(rets)
    f1 = np.zeros_like(rets)
    f2 = np.zeros_like(rets)
    for i in range(len(rets)):
        lo5 = max(0, i - 4)
        lo22 = max(0, i - 21)
        f1[i] = abs_ret[lo5 : i + 1].mean()
        f2[i] = abs_ret[lo22 : i + 1].mean()
    features = np.column_stack([log_ret, f1, f2])

    detector = HMMRegimeDetector(n_states=3, n_iter=200)
    try:
        detector.fit(features)
        result = detector.predict(features)
    except Exception as exc:
        log.debug("HMM fit/predict failed: %s", exc)
        return None
    last_state = int(result.states[-1])
    last_prob = float(result.state_probs[-1].max())
    return last_state, last_prob, result.converged


async def hmm_regime_signal(session: AsyncSession, asset: str) -> MlSignal:
    rets = await _daily_returns(session, asset, days=250)
    if len(rets) < 60:
        return MlSignal(
            name="HMM régime",
            value="n/a — insufficient daily history (< 60 obs)",
            status="placeholder",
        )
    out = await asyncio.to_thread(_hmm_compute, rets)
    if out is None:
        return MlSignal(
            name="HMM régime",
            value="n/a — ichor_ml import failed (install [ml] extras)",
            status="placeholder",
        )
    state, prob, converged = out
    state_label = {0: "low-vol trending", 1: "high-vol trending", 2: "mean-reverting noise"}[state]
    conv_tag = "" if converged else " (not converged)"
    return MlSignal(
        name="HMM régime",
        value=f"state={state} ({state_label}), p={prob:.2f}{conv_tag}",
        status="ok",
    )


# ─────────────────────────────────────────────────────────────────────
# HAR-RV — fit OLS on daily realized vol, predict h=1/5/22
# ─────────────────────────────────────────────────────────────────────


def _harrv_compute(returns: list[float]) -> tuple[float, float, float] | None:
    try:
        import numpy as np
        import pandas as pd
        from ichor_ml.vol import HARRVModel
    except ImportError as exc:
        log.debug("ichor_ml.vol import failed: %s", exc)
        return None

    rets = np.asarray(returns, dtype=np.float64)
    if rets.size < 30:
        return None

    # Daily realized vol proxy: |r_t| * sqrt(252) (annualized).
    # Cleaner alternative would be intraday-aggregated RV, but daily |return|
    # is the standard proxy when only close-to-close is available.
    rv = pd.Series(np.abs(rets) * np.sqrt(252.0))
    model = HARRVModel()
    try:
        model.fit(rv)
        pred = model.predict()
    except Exception as exc:
        log.debug("HAR-RV fit/predict failed: %s", exc)
        return None
    return pred.next_day_rv, pred.next_week_rv, pred.next_month_rv


async def har_rv_signal(session: AsyncSession, asset: str) -> MlSignal:
    rets = await _daily_returns(session, asset, days=120)
    if len(rets) < 30:
        return MlSignal(
            name="HAR-RV vol forecast",
            value="n/a — insufficient history (< 30 daily obs)",
            status="placeholder",
        )
    out = await asyncio.to_thread(_harrv_compute, rets)
    if out is None:
        return MlSignal(
            name="HAR-RV vol forecast",
            value="n/a — ichor_ml.vol import failed (install [ml] extras)",
            status="placeholder",
        )
    h1, h5, h22 = out
    return MlSignal(
        name="HAR-RV vol forecast",
        value=f"J+1={h1 * 100:.2f}% · J+5={h5 * 100:.2f}% · J+22={h22 * 100:.2f}% (annualized)",
        horizon="J+1 / J+5 / J+22",
        status="ok",
    )


# ─────────────────────────────────────────────────────────────────────
# VPIN — bulk-volume classification on Polygon FX quote stream (fx_ticks).
# Needs ~6h of quote ticks at major-pair frequency to bootstrap.
# ─────────────────────────────────────────────────────────────────────


_VPIN_MIN_TICKS = 600  # bvc_sigma_lookback (500) + 100 buffer
_VPIN_LOOKBACK_HOURS = 24


def _vpin_compute(rows: list[tuple[datetime, float, float]]) -> tuple[float, int] | None:
    """Sync compute (called via to_thread). Returns (latest_vpin, n_buckets) or None."""
    try:
        import pandas as pd
        from ichor_ml.microstructure.vpin import compute_vpin_from_fx_quotes
    except ImportError as exc:
        log.debug("ichor_ml.microstructure.vpin import failed: %s", exc)
        return None

    quotes = pd.DataFrame(
        [{"timestamp": ts, "bid": float(bid), "ask": float(ask)} for ts, bid, ask in rows]
    )
    try:
        result = compute_vpin_from_fx_quotes(
            quotes,
            bucket_n_ticks=200,
            window_n_buckets=50,
            bvc_sigma_lookback=500,
        )
    except ValueError as exc:
        log.debug("VPIN compute rejected input: %s", exc)
        return None
    except Exception as exc:
        log.debug("VPIN compute failed: %s", exc)
        return None
    latest = result.latest
    if latest is None:
        return None
    return latest, result.n_buckets


async def vpin_signal(session: AsyncSession, asset: str) -> MlSignal:
    cutoff = datetime.now(UTC) - timedelta(hours=_VPIN_LOOKBACK_HOURS)
    rows = (
        await session.execute(
            select(FxTick.ts, FxTick.bid, FxTick.ask)
            .where(FxTick.asset == asset, FxTick.ts >= cutoff)
            .order_by(FxTick.ts.asc())
        )
    ).all()
    if len(rows) < _VPIN_MIN_TICKS:
        return MlSignal(
            name="VPIN microstructure",
            value=(
                f"n/a — only {len(rows)} fx_ticks for {asset} in last "
                f"{_VPIN_LOOKBACK_HOURS}h (need {_VPIN_MIN_TICKS}+) ; "
                f"polygon_fx_stream may be lagging"
            ),
            status="placeholder",
        )
    out = await asyncio.to_thread(_vpin_compute, rows)
    if out is None:
        return MlSignal(
            name="VPIN microstructure",
            value=(
                "n/a — ichor_ml.microstructure.vpin import failed "
                "(install [ml] extras with pandas + scipy)"
            ),
            status="placeholder",
        )
    vpin, n_buckets = out
    # VPIN ∈ [0, 1] ; > 0.30 is conventionally "elevated toxicity"
    band = "elevated" if vpin > 0.30 else "normal" if vpin > 0.15 else "low"
    return MlSignal(
        name="VPIN microstructure",
        value=(
            f"{vpin:.3f} ({band} toxicity) on {n_buckets} buckets "
            f"of {len(rows)} ticks — last {_VPIN_LOOKBACK_HOURS}h"
        ),
        status="ok",
    )


# ─────────────────────────────────────────────────────────────────────
# DTW analogues — already a standalone block via services/analogues.py
# ─────────────────────────────────────────────────────────────────────


async def dtw_analogues_signal(session: AsyncSession, asset: str) -> MlSignal:
    return MlSignal(
        name="DTW analogues",
        value="see `analogues` section below for top-3 historical matches",
        status="ok",
    )


# ─────────────────────────────────────────────────────────────────────
# ADWIN drift on Brier residuals from predictions_audit
# ─────────────────────────────────────────────────────────────────────


def _adwin_compute(values: list[float]) -> tuple[bool, int | None] | None:
    """Returns (drift_detected, last_drift_idx) or None on import failure."""
    try:
        from ichor_ml.regime.concept_drift import DriftMonitor
    except ImportError as exc:
        log.debug("ichor_ml.regime.concept_drift import failed: %s", exc)
        return None

    monitor = DriftMonitor()
    last_idx: int | None = None
    drift_seen = False
    for v in values:
        events = monitor.update(float(v))
        for e in events:
            if e.detector_name == "ADWIN":
                drift_seen = True
                last_idx = e.series_index
    return drift_seen, last_idx


async def adwin_drift_signal(session: AsyncSession, asset: str) -> MlSignal:
    rows = (
        (
            await session.execute(
                select(Prediction.brier_contribution)
                .where(
                    Prediction.asset == asset,
                    Prediction.brier_contribution.is_not(None),
                )
                .order_by(Prediction.generated_at.asc())
                .limit(500)
            )
        )
        .scalars()
        .all()
    )
    series = [float(v) for v in rows if v is not None]
    if len(series) < 30:
        return MlSignal(
            name="ADWIN concept drift",
            value=f"n/a — only {len(series)} resolved predictions for {asset} (need 30+)",
            status="placeholder",
        )
    out = await asyncio.to_thread(_adwin_compute, series)
    if out is None:
        return MlSignal(
            name="ADWIN concept drift",
            value="n/a — river not installed",
            status="placeholder",
        )
    drift, idx = out
    if drift:
        return MlSignal(
            name="ADWIN concept drift",
            value=f"⚠ drift detected at series index {idx} of {len(series)}",
            status="ok",
        )
    return MlSignal(
        name="ADWIN concept drift",
        value=f"no drift on {len(series)} Brier residuals (clean)",
        status="ok",
    )


# ─────────────────────────────────────────────────────────────────────
# FOMC-RoBERTa — lazy HF load, run on recent Fed speeches
# ─────────────────────────────────────────────────────────────────────


def _fomc_roberta_compute(texts: list[str]) -> tuple[float, int, int] | None:
    """Returns (net_hawkish_score, n_speeches, n_chunks) or None on import failure.

    Long FOMC texts (minutes, press conferences) are chunked into 480-
    token windows so the RoBERTa-large 512-token limit doesn't truncate
    silently — `score_long_fomc_text` returns one FomcToneScore per
    chunk, then we aggregate across chunks AND speeches.
    """
    try:
        from ichor_ml.nlp.fomc_roberta import (
            aggregate_fomc_chunks,
            score_long_fomc_text,
        )
    except ImportError as exc:
        log.debug("ichor_ml.nlp.fomc_roberta import failed: %s", exc)
        return None

    try:
        all_chunks = []
        n_speeches = 0
        for t in texts:
            if not t.strip():
                continue
            chunk_scores = score_long_fomc_text(t)
            if chunk_scores:
                all_chunks.extend(chunk_scores)
                n_speeches += 1
    except Exception as exc:
        log.debug("FOMC-RoBERTa score failed (HF model unavailable?): %s", exc)
        return None

    if not all_chunks:
        return None
    agg = aggregate_fomc_chunks(all_chunks)
    return float(agg["net_hawkish"]), n_speeches, len(all_chunks)


async def fomc_roberta_signal(session: AsyncSession) -> MlSignal:
    cutoff = datetime.now(UTC) - timedelta(days=14)
    rows = (
        (
            await session.execute(
                select(CbSpeech)
                .where(
                    CbSpeech.central_bank == "FED",
                    CbSpeech.published_at >= cutoff,
                )
                .order_by(desc(CbSpeech.published_at))
                .limit(8)
            )
        )
        .scalars()
        .all()
    )
    texts = [r.summary or r.title for r in rows if (r.summary or r.title)]
    if len(texts) < 2:
        return MlSignal(
            name="FOMC-RoBERTa",
            value=f"n/a — only {len(texts)} Fed speeches in last 14d (need 2+)",
            status="placeholder",
        )
    out = await asyncio.to_thread(_fomc_roberta_compute, texts)
    if out is None:
        return MlSignal(
            name="FOMC-RoBERTa",
            value="n/a — model load failed (transformers/onnx not in env)",
            status="placeholder",
        )
    score, n_speeches, n_chunks = out
    direction = "hawkish" if score > 0.05 else "dovish" if score < -0.05 else "neutral"
    return MlSignal(
        name="FOMC-RoBERTa",
        value=(f"{direction} (score={score:+.2f}, n={n_speeches} speeches / {n_chunks} chunks)"),
        status="ok",
    )


# ─────────────────────────────────────────────────────────────────────
# FinBERT-tone — aggregate already-populated `news_items.tone_score`
# ─────────────────────────────────────────────────────────────────────


async def finbert_tone_signal(session: AsyncSession, asset: str) -> MlSignal:
    """Aggregate FinBERT tone from `news_items` (populated by tone worker).

    The worker runs FinBERT-tone in batch and writes `tone_score` per row.
    Here we just compute a recent mean. If nothing is populated yet, we
    return a placeholder explaining the worker hasn't run.
    """
    cutoff = datetime.now(UTC) - timedelta(hours=24)
    rows = (
        await session.execute(
            select(NewsItem.tone_score, NewsItem.tone_label)
            .where(
                NewsItem.tone_score.is_not(None),
                NewsItem.published_at >= cutoff,
            )
            .order_by(desc(NewsItem.published_at))
            .limit(200)
        )
    ).all()
    scored = [(float(s), lbl) for s, lbl in rows if s is not None]
    if len(scored) < 5:
        return MlSignal(
            name="FinBERT-tone",
            value=f"n/a — only {len(scored)} tone-tagged news in last 24h (worker pending)",
            status="placeholder",
        )
    mean = sum(s for s, _ in scored) / len(scored)
    pos = sum(1 for _, lbl in scored if lbl == "positive")
    neg = sum(1 for _, lbl in scored if lbl == "negative")
    return MlSignal(
        name="FinBERT-tone",
        value=f"mean={mean:+.2f} · pos={pos} / neg={neg} / total={len(scored)}",
        status="ok",
    )


# ─────────────────────────────────────────────────────────────────────
# SABR-SVI — explicitly deferred per SPEC §2.2 #15
# ─────────────────────────────────────────────────────────────────────


async def sabr_svi_signal(session: AsyncSession, asset: str) -> MlSignal:
    """SABR-Hagan + SVI raw fits are READY in `ichor_ml.vol.sabr_svi`.

    What's still missing : an options-chain table per (asset, expiry, strike,
    iv) populated by an upstream feed (OANDA / Tradier / Polygon options).
    `yfinance_options` collector returns chains but does not persist them
    in a queryable shape yet. Once that lands, this adapter will :
      1. Pull the latest IV smile per tenor for `asset`
      2. Call `fit_sabr_smile` (or `fit_svi_smile`) per tenor
      3. Emit 25d-risk-reversal + IV30/IV90 term ratio as features
    """
    return MlSignal(
        name="SABR-SVI IV skew",
        value=(
            "n/a — fit ready (ichor_ml.vol.sabr_svi.fit_sabr_smile) ; "
            "awaiting options-chain table population by upstream feed"
        ),
        status="placeholder",
    )


# ─────────────────────────────────────────────────────────────────────
# Block render
# ─────────────────────────────────────────────────────────────────────


async def render_ml_signals_block(session: AsyncSession, asset: str) -> tuple[str, list[str]]:
    """Consolidated ML signals block for the data_pool.

    Surfaces the 8 ML models in one section so Pass 1/2 have a single
    anchor point. Each row reports its training/wiring status honestly.
    """
    asset_adapters: list[Callable[[AsyncSession, str], Awaitable[MlSignal]]] = [
        hmm_regime_signal,
        har_rv_signal,
        vpin_signal,
        dtw_analogues_signal,
        adwin_drift_signal,
        finbert_tone_signal,
        sabr_svi_signal,
    ]
    signals: list[MlSignal] = []
    for fn in asset_adapters:
        try:
            sig = await fn(session, asset)
        except Exception as exc:
            log.warning("ml_signals adapter %s failed: %s", fn.__name__, exc)
            sig = MlSignal(name=fn.__name__, value=f"error: {exc}", status="error")
        signals.append(sig)

    # FOMC-RoBERTa is asset-agnostic (Fed-only).
    try:
        signals.append(await fomc_roberta_signal(session))
    except Exception as exc:
        log.warning("fomc_roberta_signal failed: %s", exc)
        signals.append(MlSignal(name="FOMC-RoBERTa", value=f"error: {exc}", status="error"))

    lines = [
        "## ML signals (8 models — wiring status)",
        "",
        "| Model | Status | Output |",
        "| --- | --- | --- |",
    ]
    sources: list[str] = []
    for s in signals:
        emoji = {"ok": "✓", "placeholder": "·", "error": "✗"}.get(s.status, "·")
        lines.append(f"| {s.name} | {emoji} {s.status} | {s.value} |")
        if s.status == "ok":
            sources.append(f"ml:{s.name}")
    return "\n".join(lines), sources
