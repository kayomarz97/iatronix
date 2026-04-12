"""Embedding service using SentenceTransformers.

Vector features are enabled using a local SentenceTransformer model.
"""

from __future__ import annotations

import logging
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)


class Embedder:
    _instance = None

    def __init__(self) -> None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError:
            raise RuntimeError(
                "sentence-transformers is not installed. "
                "Please add it to your requirements to use Embedder."
            )

        model_name = "google/embeddinggemma-300m"
        if settings.embedding_model and settings.embedding_model != "disabled":
            model_name = settings.embedding_model

        logger.info(f"Loading SentenceTransformer model: {model_name}")
        self.model = SentenceTransformer(model_name)
        self.expected_dim = settings.embedding_dim

    @classmethod
    def get_instance(cls) -> "Embedder":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _truncate_or_pad(self, embedding: list[float]) -> list[float]:
        """Ensure embedding matches the expected dimension (e.g., 768)."""
        if len(embedding) > self.expected_dim:
            return embedding[: self.expected_dim]
        elif len(embedding) < self.expected_dim:
            return embedding + [0.0] * (self.expected_dim - len(embedding))
        return embedding

    def embed_text(self, text: str) -> list[float]:
        """Embed a single text string."""
        import numpy as np
        
        # Output is either numpy array or tensor depending on SentenceTransformer version/config
        result = self.model.encode(text)
        if isinstance(result, np.ndarray):
            embedding = result.tolist()
        else:
            embedding = list(result)
            
        return self._truncate_or_pad(embedding)

    def embed_texts(self, texts: list[str], batch_size: int = 32) -> list[list[float]]:
        """Embed a batch of text strings."""
        import numpy as np

        results = self.model.encode(texts, batch_size=batch_size)
        
        embeddings = []
        for result in results:
            if isinstance(result, np.ndarray):
                emb = result.tolist()
            else:
                emb = list(result)
            embeddings.append(self._truncate_or_pad(emb))

        return embeddings
