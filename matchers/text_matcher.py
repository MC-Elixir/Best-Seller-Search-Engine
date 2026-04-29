"""文本相似度匹配。

MVP 使用字符 n-gram + Jaccard 作为默认打分，避免强制下载模型。
配置 `USE_EMBEDDINGS=true` 时可切换 sentence-transformers（可选）。
"""
from __future__ import annotations

import logging
import os
import re
from functools import lru_cache

logger = logging.getLogger(__name__)

_WORD_RE = re.compile(r"[A-Za-z0-9一-鿿]+")


def _tokens(text: str) -> set[str]:
    text = text.lower()
    words = _WORD_RE.findall(text)
    grams: set[str] = set(words)
    joined = "".join(words)
    for i in range(len(joined) - 2):
        grams.add(joined[i : i + 3])
    return grams


def jaccard(a: str, b: str) -> float:
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


class TextMatcher:
    def __init__(self, use_embeddings: bool | None = None) -> None:
        env_flag = os.getenv("USE_EMBEDDINGS", "").lower() in {"1", "true", "yes"}
        self.use_embeddings = env_flag if use_embeddings is None else use_embeddings
        self._model = None

    @lru_cache(maxsize=1)
    def _load_model(self):  # pragma: no cover - optional heavy dep
        from sentence_transformers import SentenceTransformer

        return SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")

    def similarity(self, a: str, b: str) -> float:
        if not a or not b:
            return 0.0
        if self.use_embeddings:
            try:  # pragma: no cover
                model = self._load_model()
                import numpy as np

                embs = model.encode([a, b], normalize_embeddings=True)
                return float(np.dot(embs[0], embs[1]))
            except Exception as e:
                logger.warning("embedding similarity unavailable (%s), fallback to jaccard", e)
        return jaccard(a, b)
