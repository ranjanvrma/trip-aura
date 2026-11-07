"""Local deep-learning text embeddings (ONNX, via fastembed) used for:

- semantic interest matching: "street art", "history buff" or "sunsets" matched against
  place names, descriptions and categories, even when no keyword overlaps;
- review sentiment: zero-shot polarity of review sentences (similarity to positive vs
  negative prototypes), combined with a lexicon in sentiment.py.

The model (default BAAI/bge-small-en-v1.5, ~65 MB) is downloaded once and runs on CPU.
If fastembed is missing or the model cannot be loaded, `available` is False and callers
fall back to lexical matching; the status endpoint reports which one is active.
"""
from __future__ import annotations

import hashlib
import logging
import threading
from pathlib import Path

log = logging.getLogger(__name__)


class SemanticMatcher:
    def __init__(self, model_name: str, cache_dir: str, enabled: bool = True):
        self.model_name = model_name
        self.cache_dir = str(Path(cache_dir) / "models")
        self.enabled = enabled
        self._model = None
        self._error: str | None = None
        self._lock = threading.Lock()
        self._cache: dict[str, object] = {}   # text hash -> embedding (numpy array)

    @property
    def status(self) -> str:
        if not self.enabled:
            return "disabled"
        if self._model is not None:
            return f"loaded ({self.model_name})"
        return f"unavailable: {self._error}" if self._error else "not loaded yet"

    @property
    def available(self) -> bool:
        return self._ensure() is not None

    def _ensure(self):
        if not self.enabled or self._error:
            return None
        if self._model is None:
            with self._lock:
                if self._model is None and not self._error:
                    try:
                        from fastembed import TextEmbedding

                        self._model = TextEmbedding(self.model_name, cache_dir=self.cache_dir)
                        log.info("Semantic model %s loaded", self.model_name)
                    except Exception as exc:  # missing package, download failure, ...
                        self._error = f"{exc.__class__.__name__}: {str(exc)[:120]}"
                        log.warning("Semantic matching unavailable (%s); using lexical matching", self._error)
        return self._model

    def embed(self, texts: list[str], query: bool = False):
        """Normalised embeddings (numpy array, one row per text). Cached per text."""
        import numpy as np

        model = self._ensure()
        if model is None:
            raise RuntimeError("semantic model unavailable")
        keys = [("q:" if query else "d:") + hashlib.sha1(t.encode("utf-8")).hexdigest() for t in texts]
        missing = [(k, t) for k, t in zip(keys, texts) if k not in self._cache]
        if missing:
            gen = model.query_embed([t for _, t in missing]) if query else model.embed([t for _, t in missing])
            for (k, _), v in zip(missing, gen):
                v = np.asarray(v, dtype="float32")
                self._cache[k] = v / (np.linalg.norm(v) or 1.0)
            if len(self._cache) > 50_000:
                self._cache.clear()
        return np.stack([self._cache[k] for k in keys])

    def similarity(self, queries: list[str], docs: list[str]):
        """Cosine similarity matrix [len(queries) x len(docs)]."""
        if not queries or not docs:
            import numpy as np
            return np.zeros((len(queries), len(docs)))
        return self.embed(queries, query=True) @ self.embed(docs).T


# Similarity -> 0..1 match strength. bge-small gives ~0.5 for unrelated text and
# ~0.75+ for a clear topical match.
SIM_FLOOR = 0.66
SIM_FULL = 0.80


def strength(sim: float) -> float:
    if sim <= SIM_FLOOR:
        return 0.0
    return min(1.0, (sim - SIM_FLOOR) / (SIM_FULL - SIM_FLOOR))
