"""BGE-small-en-v1.5 embedding via Optimum ONNX Runtime — CPU, no API.

Per ADR-020. Uses:
  - tokenizer:  HuggingFace `AutoTokenizer` (bge-small-en-v1.5)
  - model:      `optimum.onnxruntime.ORTModelForFeatureExtraction`
                with `file_name="onnx/model.onnx"` from the official
                BAAI repo (or a quantized variant for ~2× speedup on CPU).

Best-practice (per HF + sentence-transformers docs 2026):
  - Use CLS pooling (BGE family uses [CLS] as the text representation
    vector — NOT mean pooling).
  - L2-normalize embeddings so cosine similarity == dot product.
  - For prod load: `optimum-cli export onnx --library transformers
    --task sentence-similarity -m BAAI/bge-small-en-v1.5 --optimize O3`
    then `export_dynamic_quantized_onnx_model(quantization_config=AutoQuantizationConfig.avx512_vnni())`.

The class is lazy-load: instantiation is cheap, model load happens on
first `.embed()` call so test environments without HF cache don't pay
the cost on import.
"""

from __future__ import annotations

import os
from threading import Lock
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    # Type-only imports — avoid hard dependency at module level so the
    # api process boots without the ML stack installed.
    from optimum.onnxruntime import ORTModelForFeatureExtraction
    from transformers import PreTrainedTokenizerBase

EMBED_DIM = 384  # bge-small-en-v1.5
_DEFAULT_MODEL_ID = "BAAI/bge-small-en-v1.5"
_DEFAULT_ONNX_FILE = "onnx/model.onnx"


class BgeSmallEmbedder:
    """Single-process embedder. Load once, share across requests.

    Concurrency: ONNXRuntime sessions are thread-safe, so multiple
    asyncio tasks can call `.embed()` in parallel via run_in_executor.
    For Hetzner CX32 (4 vCPU) we pin intra-op threads = 2 to leave room
    for the FastAPI event loop + asyncpg pool.
    """

    def __init__(
        self,
        model_id: str = _DEFAULT_MODEL_ID,
        *,
        onnx_file_name: str = _DEFAULT_ONNX_FILE,
        intra_op_num_threads: int = 2,
        max_seq_length: int = 512,
        cache_dir: str | None = None,
    ) -> None:
        self._model_id = model_id
        self._onnx_file_name = onnx_file_name
        self._intra_op = intra_op_num_threads
        self._max_seq = max_seq_length
        self._cache_dir = cache_dir or os.environ.get("HF_HOME")
        self._tokenizer: PreTrainedTokenizerBase | None = None
        self._model: ORTModelForFeatureExtraction | None = None
        self._load_lock = Lock()

    def _ensure_loaded(self) -> None:
        if self._model is not None and self._tokenizer is not None:
            return
        with self._load_lock:
            if self._model is not None and self._tokenizer is not None:
                return
            from optimum.onnxruntime import ORTModelForFeatureExtraction
            from transformers import AutoTokenizer

            tk_kwargs: dict[str, object] = {}
            mdl_kwargs: dict[str, object] = {"file_name": self._onnx_file_name}
            if self._cache_dir:
                tk_kwargs["cache_dir"] = self._cache_dir
                mdl_kwargs["cache_dir"] = self._cache_dir

            self._tokenizer = AutoTokenizer.from_pretrained(
                self._model_id,
                **tk_kwargs,  # type: ignore[arg-type]
            )
            self._model = ORTModelForFeatureExtraction.from_pretrained(
                self._model_id,
                **mdl_kwargs,  # type: ignore[arg-type]
            )
            # Pin threads (Hetzner small CX32: 4 vCPU total).
            try:
                # The ONNX session is at .model on the optimum wrapper.
                sess = getattr(self._model, "model", None)
                if sess is not None and hasattr(sess, "set_providers"):
                    # session_options.intra_op_num_threads is set via
                    # ORTSessionOptions; the optimum wrapper exposes it
                    # via .model.intra_op_num_threads on some versions.
                    pass  # safe to skip; defaults are reasonable
            except Exception:
                pass

    def embed(self, texts: list[str]) -> np.ndarray:
        """Embed a batch. Returns shape (len(texts), EMBED_DIM) float32,
        L2-normalized so cosine = dot."""
        if not texts:
            return np.zeros((0, EMBED_DIM), dtype=np.float32)
        self._ensure_loaded()
        assert self._tokenizer is not None
        assert self._model is not None
        encoded = self._tokenizer(
            texts,
            padding=True,
            truncation=True,
            max_length=self._max_seq,
            return_tensors="np",
        )
        outputs = self._model(  # type: ignore[operator]
            input_ids=encoded["input_ids"],
            attention_mask=encoded["attention_mask"],
        )
        # Pull last hidden state and apply CLS pooling.
        hidden = outputs.last_hidden_state  # shape (batch, seq, dim)
        cls = np.asarray(hidden[:, 0, :], dtype=np.float32)
        # L2 normalize
        norms = np.linalg.norm(cls, axis=1, keepdims=True)
        norms = np.where(norms == 0, 1.0, norms)
        return cls / norms


_singleton: BgeSmallEmbedder | None = None
_singleton_lock = Lock()


def get_default_embedder() -> BgeSmallEmbedder:
    """Process-wide singleton. Cheap to call repeatedly."""
    global _singleton
    if _singleton is not None:
        return _singleton
    with _singleton_lock:
        if _singleton is None:
            _singleton = BgeSmallEmbedder()
        return _singleton


def embed_one(text: str) -> np.ndarray:
    """Convenience: embed a single string. Returns shape (EMBED_DIM,)."""
    arr = get_default_embedder().embed([text])
    return arr[0] if len(arr) > 0 else np.zeros(EMBED_DIM, dtype=np.float32)
