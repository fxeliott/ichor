"""ML model loader — lazy + cached load of trained model artifacts.

Per ADR-021 + AUTOEVO §2. Each scaffolded ML model in
`packages/ml/src/ichor_ml/` should ship a .pkl/.onnx artifact in
`packages/ml/.cache/` once trained. This loader provides:

  - `load_hmm(asset)`              → trained HMM regime detector
  - `load_har_rv(asset)`           → trained HAR-RV vol forecaster
  - `load_finbert_tone()`          → HuggingFace pipeline (HF cache)
  - `load_fomc_roberta()`          → HuggingFace pipeline (HF cache)
  - `load_sabr_svi(asset)`         → SABR-SVI calibration (vollib)

All functions return None if the artifact is missing — production must
check and gracefully fall back to placeholder output (the data_pool
ml_signals adapter already does this).

Phase B follow-up: each model trainer (regime/hmm.py, vol/har_rv.py)
must persist its fitted state to `packages/ml/.cache/<asset>.pkl` after
training; cron `train-ml-models.timer` re-trains weekly on Sunday 22:00.
"""

from __future__ import annotations

import logging
import os
import pickle
from pathlib import Path
from threading import Lock
from typing import Any

log = logging.getLogger(__name__)

# Lazy singletons (loaded once per process, shared across requests).
_MODEL_CACHE: dict[str, Any] = {}
_LOCK = Lock()

# Default cache dir; overridable via env var.
DEFAULT_CACHE_DIR = Path(os.environ.get("ICHOR_ML_CACHE_DIR", "/opt/ichor/ml-cache"))


def _cache_path(name: str) -> Path:
    return DEFAULT_CACHE_DIR / name


def _load_pickle(name: str) -> Any | None:
    path = _cache_path(name)
    if not path.exists():
        return None
    try:
        with path.open("rb") as f:
            return pickle.load(f)  # noqa: S301 — pickle is fine for our own artifacts
    except (OSError, pickle.UnpicklingError) as exc:
        log.warning("ml_loader.load_failed name=%s error=%s", name, exc)
        return None


def load_hmm(asset: str) -> Any | None:
    """Trained HMM regime detector for `asset`.

    Returns None if no fitted model on disk yet — caller should fall
    back to a placeholder signal (cf services/ml_signals.py).
    """
    cache_key = f"hmm:{asset}"
    if cache_key in _MODEL_CACHE:
        return _MODEL_CACHE[cache_key]
    with _LOCK:
        if cache_key in _MODEL_CACHE:
            return _MODEL_CACHE[cache_key]
        model = _load_pickle(f"hmm-{asset.lower()}.pkl")
        if model is not None:
            _MODEL_CACHE[cache_key] = model
        return model


def load_har_rv(asset: str) -> Any | None:
    """Trained HAR-RV vol forecaster for `asset`."""
    cache_key = f"har_rv:{asset}"
    if cache_key in _MODEL_CACHE:
        return _MODEL_CACHE[cache_key]
    with _LOCK:
        if cache_key in _MODEL_CACHE:
            return _MODEL_CACHE[cache_key]
        model = _load_pickle(f"har_rv-{asset.lower()}.pkl")
        if model is not None:
            _MODEL_CACHE[cache_key] = model
        return model


def load_finbert_tone() -> Any | None:
    """HuggingFace `yiyanghkust/finbert-tone` pipeline.

    Lazy import: if `transformers` isn't installed, returns None.
    """
    cache_key = "finbert_tone"
    if cache_key in _MODEL_CACHE:
        return _MODEL_CACHE[cache_key]
    with _LOCK:
        if cache_key in _MODEL_CACHE:
            return _MODEL_CACHE[cache_key]
        try:
            from transformers import pipeline

            pipe = pipeline(
                "text-classification",
                model="yiyanghkust/finbert-tone",
                device=-1,  # CPU
            )
            _MODEL_CACHE[cache_key] = pipe
            return pipe
        except ImportError:
            log.warning("ml_loader.finbert_tone.transformers_missing")
            return None
        except Exception as exc:
            log.warning("ml_loader.finbert_tone.load_failed error=%s", exc)
            return None


def load_fomc_roberta() -> Any | None:
    """HuggingFace `gtfintechlab/FOMC-RoBERTa` pipeline."""
    cache_key = "fomc_roberta"
    if cache_key in _MODEL_CACHE:
        return _MODEL_CACHE[cache_key]
    with _LOCK:
        if cache_key in _MODEL_CACHE:
            return _MODEL_CACHE[cache_key]
        try:
            from transformers import pipeline

            pipe = pipeline(
                "text-classification",
                model="gtfintechlab/FOMC-RoBERTa",
                device=-1,
            )
            _MODEL_CACHE[cache_key] = pipe
            return pipe
        except ImportError:
            log.warning("ml_loader.fomc_roberta.transformers_missing")
            return None
        except Exception as exc:
            log.warning("ml_loader.fomc_roberta.load_failed error=%s", exc)
            return None


def is_loaded(name: str) -> bool:
    """Diagnostic: has the model been loaded at least once in this process?"""
    return name in _MODEL_CACHE


def status() -> dict[str, bool]:
    """Diagnostic: mapping of all known model keys → loaded/not."""
    return dict.fromkeys(_MODEL_CACHE, True)
