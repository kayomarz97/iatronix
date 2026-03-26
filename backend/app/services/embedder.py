"""Local embedding service using sentence-transformers (all-MiniLM-L6-v2).

Zero API cost. ~90MB RAM. ~5-10ms per embedding on CPU.
Singleton pattern ensures only one model copy in memory.
"""

import logging

from app.config import settings

logger = logging.getLogger(__name__)


class Embedder:
    _instance = None
    _model = None

    @classmethod
    def get_instance(cls) -> "Embedder":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _load_model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            logger.info("Loading embedding model: %s", settings.embedding_model)
            self._model = SentenceTransformer(settings.embedding_model)
            logger.info("Embedding model loaded (%d dims)", settings.embedding_dim)

    def embed_text(self, text: str) -> list[float]:
        """Embed a single text string. Returns normalized vector."""
        self._load_model()
        return self._model.encode(text, normalize_embeddings=True).tolist()

    def embed_texts(self, texts: list[str], batch_size: int = 32) -> list[list[float]]:
        """Embed multiple texts in batch. Returns list of normalized vectors."""
        self._load_model()
        return self._model.encode(
            texts, batch_size=batch_size, normalize_embeddings=True
        ).tolist()
