"""Tests for the 3 sibling bias trainers : XGBoost / RandomForest / Logistic.

LightGBM is covered in `test_features_and_lightgbm.py` — the four share
the same training interface so this file uses a parametrize-by-trainer
matrix to exercise the contract once.

Each trainer returns a wrapper exposing :
  - `.artifact.asset` (carries through from bars[0].asset)
  - `.artifact.feature_names` (== FEATURE_NAMES)
  - `.artifact.train_brier` ∈ [0, 1]
  - `.predict_proba(feature_row)` ∈ [0, 1]

And refuses to train on series too short to produce ≥30 feature rows.
"""

from __future__ import annotations

import importlib.util
import pathlib
from datetime import date, timedelta

import pytest

# Direct file load to avoid pulling ichor_ml.__init__ heavy ML deps.
_TRAINING_DIR = pathlib.Path(__file__).resolve().parents[1] / "src" / "ichor_ml" / "training"


def _load(name: str):  # type: ignore[no-untyped-def]
    """Import `ichor_ml.training.{name}` as a regular module.

    Adds packages/ml/src to sys.path so relative imports inside the
    training package resolve. Skips the test if a heavy dep (xgboost /
    sklearn) isn't installed in the env.
    """
    path = _TRAINING_DIR / f"{name}.py"
    if not path.exists():
        pytest.skip(f"ichor_ml.training.{name} not yet implemented")
    import sys

    src_root = str(_TRAINING_DIR.parent.parent)  # packages/ml/src
    if src_root not in sys.path:
        sys.path.insert(0, src_root)
    try:
        return importlib.import_module(f"ichor_ml.training.{name}")
    except ImportError as e:
        pytest.skip(f"{name} import failed (heavy dep missing): {e}")
    return None  # unreachable but keeps mypy happy


def _bars(n: int, *, start_price: float = 1.0, drift: float = 0.0001):
    """Same generator as test_features_and_lightgbm.py for parity."""
    features_mod = _load("features")
    BarLike = features_mod.BarLike
    bars = []
    cursor = date(2024, 1, 1)
    price = start_price
    for i in range(n):
        op = price
        cl = price * (1 + drift + 0.0005 * (i % 5 - 2))
        hi = max(op, cl) + 0.001
        lo = min(op, cl) - 0.001
        bars.append(
            BarLike(
                bar_date=cursor + timedelta(days=i),
                asset="EUR_USD",
                open=op,
                high=hi,
                low=lo,
                close=cl,
            )
        )
        price = cl
    return bars


def _build_features(bars):  # type: ignore[no-untyped-def]
    features_mod = _load("features")
    return features_mod.build_features_daily(bars[-100:])


# Each tuple : (module_name, train_fn_attr, kwargs)
_TRAINER_MATRIX = [
    ("xgboost_bias", "train_xgboost_bias", {"n_estimators": 20}),
    ("random_forest_bias", "train_random_forest_bias", {"n_estimators": 20}),
    ("logistic_bias", "train_logistic_bias", {}),
    ("mlp_bias", "train_mlp_bias", {"max_iter": 50}),
    # NumPyro NUTS sampling — keep tests cheap.
    ("numpyro_bias", "train_numpyro_bias", {"n_samples": 50, "n_warmup": 20}),
]


@pytest.mark.parametrize(("module_name", "fn_name", "kwargs"), _TRAINER_MATRIX)
def test_train_runs_and_predicts(module_name: str, fn_name: str, kwargs: dict) -> None:
    """Each trainer fits on 500 synthetic bars and predicts on a feature row."""
    mod = _load(module_name)
    train_fn = getattr(mod, fn_name)

    bars = _bars(500)
    model = train_fn(bars, **kwargs)
    assert model.artifact.asset == "EUR_USD"

    # Feature names must be the canonical 9-tuple.
    features_mod = _load("features")
    assert model.artifact.feature_names == features_mod.FEATURE_NAMES

    # Brier ∈ [0, 1]
    assert 0.0 <= model.artifact.train_brier <= 1.0

    # predict_proba on a real feature row
    rows = _build_features(bars)
    p = model.predict_proba(rows[-1])
    assert 0.0 <= p <= 1.0


@pytest.mark.parametrize(("module_name", "fn_name", "kwargs"), _TRAINER_MATRIX)
def test_refuses_with_too_few_rows(module_name: str, fn_name: str, kwargs: dict) -> None:
    """≤ 30 feature rows after min_history → ValueError, no silent overfit."""
    mod = _load(module_name)
    train_fn = getattr(mod, fn_name)
    bars = _bars(70)  # ~9 feature rows after min_history=60
    with pytest.raises(ValueError, match=r"(?i)at least|empty"):
        train_fn(bars, **kwargs)


@pytest.mark.parametrize(("module_name", "fn_name", "kwargs"), _TRAINER_MATRIX)
def test_refuses_empty_bars(module_name: str, fn_name: str, kwargs: dict) -> None:
    mod = _load(module_name)
    train_fn = getattr(mod, fn_name)
    with pytest.raises(ValueError, match="empty"):
        train_fn([], **kwargs)


@pytest.mark.parametrize(("module_name", "fn_name", "kwargs"), _TRAINER_MATRIX)
def test_n_train_rows_matches_built_features(module_name: str, fn_name: str, kwargs: dict) -> None:
    """Artifact.n_train_rows must equal len(build_features_daily(bars))."""
    mod = _load(module_name)
    train_fn = getattr(mod, fn_name)
    features_mod = _load("features")

    bars = _bars(300)
    model = train_fn(bars, **kwargs)
    expected = len(features_mod.build_features_daily(bars))
    assert model.artifact.n_train_rows == expected


def test_training_init_exports_all_6_trainers() -> None:
    """The training package's __init__ should re-export all 6 trainers."""
    init_path = _TRAINING_DIR / "__init__.py"
    if not init_path.exists():
        pytest.skip("training/__init__.py not present")
    spec = importlib.util.spec_from_file_location("ichor_ml_training_init", init_path)
    assert spec is not None and spec.loader is not None
    # We can't exec the __init__ here without ichor_ml being importable
    # (it imports relatively from `.lightgbm_bias`), so just textually
    # check that the exports are wired.
    text = init_path.read_text(encoding="utf-8")
    for fn in (
        "train_lightgbm_bias",
        "train_xgboost_bias",
        "train_random_forest_bias",
        "train_logistic_bias",
        "train_mlp_bias",
        "train_numpyro_bias",
    ):
        assert fn in text, f"missing export: {fn}"
